"""Landing page drafts: product input, images, autosave versions."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.storage import get_storage

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_NAME_LENGTH = 200
ORDER_METHODS = frozenset({"whatsapp", "cod"})
IMAGE_TYPES = {
    "image/jpeg": (".jpg", ".jpeg"),
    "image/png": (".png",),
    "image/webp": (".webp",),
}
_IMAGE_MAGIC = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


class LandingPageError(Exception):
    """Base class for landing page contract failures."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _clean_text(value: object, name: str, *, max_length: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LandingPageError(f"invalid_{name}", f"{name} is required.")
    clean = value.strip()
    if max_length is not None and len(clean) > max_length:
        raise LandingPageError(
            f"invalid_{name}", f"{name} must be {max_length} characters or fewer."
        )
    return clean


def _optional_text(value: object, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LandingPageError(f"invalid_{name}", f"{name} must be a string.")
    return value


def _uuid_value(value: object, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise LandingPageError(f"invalid_{name}", f"{name} must be a UUID.") from exc


def _uuid_list(value: object, name: str) -> list[uuid.UUID]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise LandingPageError(f"invalid_{name}", f"{name} must be a list.")
    return [_uuid_value(item, name) for item in value]


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{base[:60] or 'page'}-{uuid.uuid4().hex[:8]}"


def _iso(value: object) -> str | None:
    return value.isoformat() if value is not None else None


def _require_active(
    session: Session, table: str, column: str, key: object, name: str
) -> None:
    exists = session.execute(
        text(f"SELECT 1 FROM {table} WHERE {column} = :key AND is_active"),
        {"key": key},
    ).scalar_one_or_none()
    if exists is None:
        raise LandingPageError(
            f"invalid_{name}", f"{name} must reference active reference data."
        )


def _validate_order_method(method: object) -> dict[str, Any]:
    if not isinstance(method, Mapping):
        raise LandingPageError(
            "invalid_order_method", "order_method must be an object."
        )
    method_type = method.get("type")
    if method_type not in ORDER_METHODS:
        raise LandingPageError(
            "invalid_order_method", "order_method.type must be whatsapp or cod."
        )
    if method_type == "whatsapp":
        number = method.get("whatsapp_number")
        if not isinstance(number, str) or not number.strip():
            raise LandingPageError(
                "invalid_order_method",
                "order_method.whatsapp_number is required for whatsapp.",
            )
        return {
            "type": "whatsapp",
            "whatsapp_number": number.strip(),
            "whatsapp_message_template": _optional_text(
                method.get("whatsapp_message_template"),
                "whatsapp_message_template",
            ),
            "cod_form_schema": None,
        }
    schema = method.get("cod_form_schema")
    if schema is not None and not isinstance(schema, Mapping):
        raise LandingPageError(
            "invalid_order_method", "cod_form_schema must be an object."
        )
    return {
        "type": "cod",
        "whatsapp_number": None,
        "whatsapp_message_template": None,
        "cod_form_schema": dict(schema or {"schema_version": 1, "fields": []}),
    }


def _validated_payload(
    session: Session, payload: Mapping[str, Any]
) -> dict[str, Any]:
    name = _clean_text(payload.get("name"), "name", max_length=MAX_NAME_LENGTH)
    description = _optional_text(payload.get("description"), "description")
    price_minor = payload.get("price_minor")
    if (
        not isinstance(price_minor, int)
        or isinstance(price_minor, bool)
        or price_minor <= 0
    ):
        raise LandingPageError(
            "invalid_price", "price_minor must be a positive integer."
        )
    currency = _clean_text(payload.get("currency"), "currency")
    language = _clean_text(payload.get("language"), "language")
    target_market = _clean_text(payload.get("target_market"), "target_market")
    _require_active(session, "currencies", "code", currency, "currency")
    _require_active(session, "languages", "code", language, "language")
    _require_active(session, "countries", "code", target_market, "target_market")
    return {
        "name": name,
        "description": description,
        "price_minor": price_minor,
        "currency": currency,
        "language": language,
        "target_market": target_market,
        "image_file_ids": _uuid_list(
            payload.get("image_file_ids"), "image_file_ids"
        ),
        "order_method": _validate_order_method(payload.get("order_method")),
    }


def _assert_images(
    session: Session, tenant: TenantContext, image_ids: list[uuid.UUID]
) -> None:
    if not image_ids:
        return
    count = session.execute(
        text(
            """
            SELECT count(*) FROM stored_files
            WHERE store_id = :store_id
              AND id = ANY(:ids)
              AND purpose = 'product_image'
              AND status <> 'deleted'
            """
        ),
        {"store_id": tenant.store_id, "ids": image_ids},
    ).scalar_one()
    if count != len(set(image_ids)):
        raise LandingPageError(
            "invalid_images", "Every image must be an owned product image."
        )


def _default_template(session: Session) -> uuid.UUID:
    template_id = session.execute(
        text("SELECT id FROM page_templates ORDER BY version, id LIMIT 1")
    ).scalar_one_or_none()
    if template_id is not None:
        return template_id
    return session.execute(
        text(
            """
            INSERT INTO page_templates (key, version, name, schema)
            VALUES ('default', 1, 'Default', '{"schema_version": 1}'::jsonb)
            RETURNING id
            """
        )
    ).scalar_one()


def _content(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "name": payload["name"],
        "description": payload["description"],
        "target_market": payload["target_market"],
    }


def _insert_version(
    session: Session,
    tenant: TenantContext,
    page_id: uuid.UUID,
    payload: Mapping[str, Any],
    order_channel_id: uuid.UUID,
    *,
    version: int,
) -> uuid.UUID:
    return session.execute(
        text(
            """
            INSERT INTO page_versions (
                store_id, landing_page_id, version, content, price_minor,
                currency, image_file_ids, order_channel_id, generated_by,
                created_by
            ) VALUES (
                :store_id, :landing_page_id, :version, :content,
                :price_minor, :currency, CAST(:image_ids AS uuid[]),
                :order_channel_id, 'manual', :created_by
            )
            RETURNING id
            """
        ),
        {
            "store_id": tenant.store_id,
            "landing_page_id": page_id,
            "version": version,
            "content": Jsonb(_content(payload)),
            "price_minor": payload["price_minor"],
            "currency": payload["currency"],
            "image_ids": payload["image_file_ids"],
            "order_channel_id": order_channel_id,
            "created_by": tenant.user_id,
        },
    ).scalar_one()


def _insert_order_channel(
    session: Session, tenant: TenantContext, page_id: uuid.UUID, method: Mapping
) -> uuid.UUID:
    return session.execute(
        text(
            """
            INSERT INTO order_channels (
                store_id, landing_page_id, type, whatsapp_number,
                whatsapp_message_template, cod_form_schema
            ) VALUES (
                :store_id, :landing_page_id, :type, :whatsapp_number,
                :whatsapp_message_template, :cod_form_schema
            )
            RETURNING id
            """
        ),
        {
            "store_id": tenant.store_id,
            "landing_page_id": page_id,
            "type": method["type"],
            "whatsapp_number": method["whatsapp_number"],
            "whatsapp_message_template": method["whatsapp_message_template"],
            "cod_form_schema": (
                Jsonb(method["cod_form_schema"])
                if method["cod_form_schema"] is not None
                else None
            ),
        },
    ).scalar_one()


def _update_order_channel(
    session: Session, tenant: TenantContext, channel_id: uuid.UUID, method: Mapping
) -> None:
    session.execute(
        text(
            """
            UPDATE order_channels
            SET type = :type,
                whatsapp_number = :whatsapp_number,
                whatsapp_message_template = :whatsapp_message_template,
                cod_form_schema = :cod_form_schema
            WHERE id = :id AND store_id = :store_id
            """
        ),
        {
            "id": channel_id,
            "store_id": tenant.store_id,
            "type": method["type"],
            "whatsapp_number": method["whatsapp_number"],
            "whatsapp_message_template": method["whatsapp_message_template"],
            "cod_form_schema": (
                Jsonb(method["cod_form_schema"])
                if method["cod_form_schema"] is not None
                else None
            ),
        },
    )


def _page_row(session: Session, tenant: TenantContext, page_id: uuid.UUID) -> Mapping:
    row = session.execute(
        text(
            """
            SELECT * FROM landing_pages
            WHERE id = :id AND store_id = :store_id AND deleted_at IS NULL
            """
        ),
        {"id": page_id, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise LandingPageError("not_found", "Landing page not found.", status_code=404)
    return row


def _page_out(
    session: Session, tenant: TenantContext, row: Mapping[str, Any]
) -> dict[str, Any]:
    version = None
    if row["current_version_id"] is not None:
        version = session.execute(
            text("SELECT * FROM page_versions WHERE id = :id"),
            {"id": row["current_version_id"]},
        ).mappings().one()
    channel = None
    if row["order_channel_id"] is not None:
        channel = session.execute(
            text("SELECT * FROM order_channels WHERE id = :id"),
            {"id": row["order_channel_id"]},
        ).mappings().one()
    return {
        "id": str(row["id"]),
        "product_concept_id": str(row["product_concept_id"]),
        "test_id": str(row["test_id"]) if row["test_id"] else None,
        "slug": row["slug"],
        "status": row["status"],
        "language": row["language"],
        "currency": row["currency"].strip(),
        "published_url": row["published_url"],
        "published_at": _iso(row["published_at"]),
        "draft_version": version["version"] if version else None,
        "price_minor": version["price_minor"] if version else None,
        "content": version["content"] if version else None,
        "image_file_ids": (
            [str(item) for item in version["image_file_ids"]] if version else []
        ),
        "order_method": (
            {
                "type": channel["type"],
                "whatsapp_number": channel["whatsapp_number"],
                "whatsapp_message_template": channel["whatsapp_message_template"],
                "cod_form_schema": channel["cod_form_schema"],
            }
            if channel
            else None
        ),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


def create_draft(
    session: Session, tenant: TenantContext, payload: Mapping[str, Any]
) -> dict[str, Any]:
    data = _validated_payload(session, payload)
    concept_id = _uuid_value(payload.get("product_concept_id"), "product_concept_id")
    concept = session.execute(
        text(
            "SELECT 1 FROM product_concepts "
            "WHERE id = :id AND store_id = :store_id AND deleted_at IS NULL"
        ),
        {"id": concept_id, "store_id": tenant.store_id},
    ).scalar_one_or_none()
    if concept is None:
        raise LandingPageError(
            "invalid_product_concept", "Product concept must belong to the store."
        )
    _assert_images(session, tenant, data["image_file_ids"])

    page_id = session.execute(
        text(
            """
            INSERT INTO landing_pages (
                store_id, product_concept_id, slug, status, template_id,
                language, currency
            ) VALUES (
                :store_id, :product_concept_id, :slug, 'draft', :template_id,
                :language, :currency
            )
            RETURNING id
            """
        ),
        {
            "store_id": tenant.store_id,
            "product_concept_id": concept_id,
            "slug": _slugify(data["name"]),
            "template_id": _default_template(session),
            "language": data["language"],
            "currency": data["currency"],
        },
    ).scalar_one()

    channel_id = _insert_order_channel(session, tenant, page_id, data["order_method"])
    version_id = _insert_version(
        session, tenant, page_id, data, channel_id, version=1
    )
    session.execute(
        text(
            """
            UPDATE landing_pages
            SET order_channel_id = :channel_id, current_version_id = :version_id
            WHERE id = :id
            """
        ),
        {
            "id": page_id,
            "channel_id": channel_id,
            "version_id": version_id,
        },
    )
    return _page_out(session, tenant, _page_row(session, tenant, page_id))


def save_draft(
    session: Session,
    tenant: TenantContext,
    page_id: uuid.UUID,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    row = _page_row(session, tenant, page_id)
    if row["status"] != "draft":
        raise LandingPageError(
            "not_draft", "Only draft landing pages can be autosaved.", status_code=409
        )
    data = _validated_payload(session, payload)
    _assert_images(session, tenant, data["image_file_ids"])

    next_version = session.execute(
        text(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM page_versions "
            "WHERE landing_page_id = :id"
        ),
        {"id": page_id},
    ).scalar_one()

    if row["order_channel_id"] is None:
        channel_id = _insert_order_channel(
            session, tenant, page_id, data["order_method"]
        )
    else:
        channel_id = row["order_channel_id"]
        _update_order_channel(session, tenant, channel_id, data["order_method"])

    version_id = _insert_version(
        session, tenant, page_id, data, channel_id, version=next_version
    )
    session.execute(
        text(
            """
            UPDATE landing_pages
            SET language = :language, currency = :currency,
                order_channel_id = :channel_id, current_version_id = :version_id
            WHERE id = :id
            """
        ),
        {
            "id": page_id,
            "language": data["language"],
            "currency": data["currency"],
            "channel_id": channel_id,
            "version_id": version_id,
        },
    )
    return _page_out(session, tenant, _page_row(session, tenant, page_id))


def get_landing_page(
    session: Session, tenant: TenantContext, page_id: uuid.UUID
) -> dict[str, Any]:
    return _page_out(session, tenant, _page_row(session, tenant, page_id))


def upload_product_image(
    session: Session,
    tenant: TenantContext,
    *,
    filename: str,
    content_type: str,
    data: bytes,
) -> dict[str, Any]:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    lower_name = (filename or "").lower()
    if normalized not in IMAGE_TYPES or not lower_name.endswith(
        IMAGE_TYPES[normalized]
    ):
        raise LandingPageError(
            "invalid_image_type", "Only JPG, PNG, or WebP images are supported."
        )
    if not data:
        raise LandingPageError("invalid_image", "The image file is empty.")
    if len(data) > MAX_IMAGE_BYTES:
        raise LandingPageError(
            "image_too_large", "Images must be 5 MB or smaller."
        )
    if not any(data.startswith(magic) for magic in _IMAGE_MAGIC[normalized]):
        raise LandingPageError(
            "invalid_image_type", "The file content does not match its image type."
        )

    stored = get_storage().save(
        data,
        filename=filename,
        content_type=normalized,
        purpose="product_image",
    )
    file_id = session.execute(
        text(
            """
            INSERT INTO stored_files (
                store_id, purpose, original_filename, mime_type, size_bytes,
                checksum_sha256, storage_provider, storage_key, status,
                uploaded_by_user_id
            ) VALUES (
                :store_id, 'product_image', :original_filename, :mime_type,
                :size_bytes, :checksum_sha256, 'local', :storage_key, 'staged',
                :uploaded_by_user_id
            )
            RETURNING id
            """
        ),
        {
            "store_id": tenant.store_id,
            "original_filename": stored.original_filename,
            "mime_type": stored.content_type,
            "size_bytes": stored.size_bytes,
            "checksum_sha256": stored.checksum_sha256,
            "storage_key": stored.key,
            "uploaded_by_user_id": tenant.user_id,
        },
    ).scalar_one()
    return {
        "id": str(file_id),
        "size_bytes": stored.size_bytes,
        "checksum_sha256": stored.checksum_sha256,
        "mime_type": stored.content_type,
    }


__all__ = [
    "MAX_IMAGE_BYTES",
    "ORDER_METHODS",
    "LandingPageError",
    "create_draft",
    "get_landing_page",
    "save_draft",
    "upload_product_image",
]
