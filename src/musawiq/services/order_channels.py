"""Order channel configuration, WhatsApp deep links, and pre-publish checks."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, parse_qs, urlsplit

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext

ORDER_TYPES = frozenset({"whatsapp", "cod"})
NUMBER_PATTERN = re.compile(r"^\+?[0-9]{8,15}$")
TOKEN_PREFIX = "lpt_"


class OrderChannelError(Exception):
    """Base class for order channel contract failures."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def attribution_token(page_id: uuid.UUID | str) -> str:
    """Stable per-page attribution token used in WhatsApp deep links."""
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, f"musawiq:landing-page:{page_id}")
    return TOKEN_PREFIX + namespace.hex[:24]


def whatsapp_link(number: str, message: str, token: str) -> str:
    digits = re.sub(r"[^0-9]", "", number)
    text = f"{message.strip()}\n\n{token}"
    return f"https://wa.me/{digits}?text={quote(text, safe='')}"


def _page(session: Session, tenant: TenantContext, page_id: object) -> Mapping:
    try:
        page_uuid = uuid.UUID(str(page_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise OrderChannelError(
            "invalid_page_id", "page_id must be a UUID."
        ) from exc
    row = session.execute(
        text(
            """
            SELECT id, current_version_id FROM landing_pages
            WHERE id = :id AND store_id = :store_id AND deleted_at IS NULL
            """
        ),
        {"id": page_uuid, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise OrderChannelError(
            "not_found", "Landing page not found.", status_code=404
        )
    return row


def _validated_fields(schema: object) -> list[dict[str, Any]]:
    if not isinstance(schema, Mapping):
        raise OrderChannelError(
            "invalid_cod_schema", "cod_form_schema must be an object."
        )
    fields = schema.get("fields")
    if not isinstance(fields, list) or not fields:
        raise OrderChannelError(
            "invalid_cod_schema", "COD requires at least one form field."
        )
    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for field in fields:
        if not isinstance(field, Mapping):
            raise OrderChannelError(
                "invalid_cod_schema", "Each COD field must be an object."
            )
        name = field.get("name")
        if not isinstance(name, str) or not name.strip():
            raise OrderChannelError(
                "invalid_cod_schema", "Each COD field needs a name."
            )
        if name in seen:
            raise OrderChannelError(
                "invalid_cod_schema", "COD field names must be unique."
            )
        seen.add(name)
        cleaned.append(
            {
                "name": name.strip(),
                "label": field.get("label") or name.strip(),
                "type": field.get("type") or "text",
                "required": bool(field.get("required", True)),
            }
        )
    if not any(field["required"] for field in cleaned):
        raise OrderChannelError(
            "invalid_cod_schema", "COD requires at least one required field."
        )
    return cleaned


def _validated_number(value: object) -> str:
    number = re.sub(r"[\s()-]", "", str(value or ""))
    if not NUMBER_PATTERN.fullmatch(number):
        raise OrderChannelError(
            "invalid_whatsapp_number",
            "whatsapp_number must be 8-15 digits, optionally prefixed with +.",
        )
    return number


def configure(
    session: Session,
    tenant: TenantContext,
    page_id: object,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    channel = _page(session, tenant, page_id)
    method = payload.get("type")
    if method not in ORDER_TYPES:
        raise OrderChannelError(
            "invalid_order_method", "type must be whatsapp or cod."
        )

    number = None
    message = None
    schema = None
    if method == "whatsapp":
        number = _validated_number(payload.get("whatsapp_number"))
        message = payload.get("whatsapp_message_template")
        if message is not None and not isinstance(message, str):
            raise OrderChannelError(
                "invalid_order_method",
                "whatsapp_message_template must be a string.",
            )
        message = (message or "").strip() or "مرحباً، أرغب بطلب هذا المنتج."
    else:
        schema = {
            "schema_version": 1,
            "fields": _validated_fields(payload.get("cod_form_schema")),
        }

    values = {
        "store_id": tenant.store_id,
        "landing_page_id": channel["id"],
        "type": method,
        "whatsapp_number": number,
        "whatsapp_message_template": message,
        "cod_form_schema": Jsonb(schema) if schema is not None else None,
    }
    existing = session.execute(
        text(
            "SELECT id FROM order_channels "
            "WHERE landing_page_id = :landing_page_id "
            "AND store_id = :store_id LIMIT 1"
        ),
        {"landing_page_id": channel["id"], "store_id": tenant.store_id},
    ).scalar_one_or_none()

    if existing is None:
        channel_id = session.execute(
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
                **values,
                "cod_form_schema": (
                    values["cod_form_schema"] if schema is not None else None
                ),
            },
        ).scalar_one()
    else:
        channel_id = existing
        session.execute(
            text(
                """
                UPDATE order_channels
                SET type = :type,
                    whatsapp_number = :whatsapp_number,
                    whatsapp_message_template = :whatsapp_message_template,
                    cod_form_schema = :cod_form_schema,
                    is_active = true
                WHERE id = :id AND store_id = :store_id
                """
            ),
            {**values, "id": channel_id},
        )

    session.execute(
        text(
            "UPDATE landing_pages SET order_channel_id = :channel_id "
            "WHERE id = :page_id AND store_id = :store_id"
        ),
        {
            "channel_id": channel_id,
            "page_id": channel["id"],
            "store_id": tenant.store_id,
        },
    )
    if channel["current_version_id"] is not None:
        session.execute(
            text(
                "UPDATE page_versions SET order_channel_id = :channel_id "
                "WHERE id = :version_id"
            ),
            {"channel_id": channel_id, "version_id": channel["current_version_id"]},
        )
    return describe(session, tenant, page_id)


def describe(
    session: Session, tenant: TenantContext, page_id: object
) -> dict[str, Any]:
    page = _page(session, tenant, page_id)
    row = session.execute(
        text(
            """
            SELECT * FROM order_channels
            WHERE landing_page_id = :landing_page_id
              AND store_id = :store_id
            ORDER BY is_active DESC, created_at
            LIMIT 1
            """
        ),
        {
            "landing_page_id": page["id"],
            "store_id": tenant.store_id,
        },
    ).mappings().one_or_none()
    if row is None:
        raise OrderChannelError(
            "not_configured", "No order channel is configured.", status_code=404
        )
    token = attribution_token(page["id"])
    link = (
        whatsapp_link(
            row["whatsapp_number"],
            row["whatsapp_message_template"] or "",
            token,
        )
        if row["type"] == "whatsapp"
        else None
    )
    return {
        "type": row["type"],
        "whatsapp_number": row["whatsapp_number"],
        "whatsapp_message_template": row["whatsapp_message_template"],
        "cod_form_schema": row["cod_form_schema"],
        "attribution_token": token,
        "whatsapp_link": link,
        "is_active": row["is_active"],
    }


def verify(
    session: Session, tenant: TenantContext, page_id: object
) -> dict[str, Any]:
    channel = describe(session, tenant, page_id)
    errors: list[str] = []
    if channel["type"] == "whatsapp":
        if not channel["whatsapp_number"] or not NUMBER_PATTERN.fullmatch(
            channel["whatsapp_number"]
        ):
            errors.append("whatsapp_number is invalid")
        if not (channel["whatsapp_message_template"] or "").strip():
            errors.append("whatsapp_message_template is empty")
        link = channel["whatsapp_link"] or ""
        parts = urlsplit(link)
        if parts.scheme != "https" or parts.netloc != "wa.me":
            errors.append("whatsapp link is not a wa.me URL")
        decoded = parse_qs(parts.query).get("text", [""])[0]
        if channel["attribution_token"] not in decoded:
            errors.append("whatsapp link is missing the attribution token")
    else:
        fields = (channel["cod_form_schema"] or {}).get("fields") or []
        if not fields:
            errors.append("cod form has no fields")
        elif not any(field.get("required") for field in fields):
            errors.append("cod form has no required fields")
    return {"valid": not errors, "errors": errors}


def token_for_page(page_id: uuid.UUID | str) -> str:
    return attribution_token(page_id)


__all__ = [
    "ORDER_TYPES",
    "OrderChannelError",
    "attribution_token",
    "configure",
    "describe",
    "token_for_page",
    "verify",
    "whatsapp_link",
]
