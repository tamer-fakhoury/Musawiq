"""Product concept draft creation and editing."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.domain.money import Money, gross_margin_bp
from musawiq.repositories.base import TenantScopedRepository
from musawiq.repositories.product_concepts import ProductConceptRepository
from musawiq.storage import get_storage
from musawiq.storage.local import DEFAULT_MAX_SIZE_BYTES, IMAGE_CONTENT_TYPES

MAX_IMAGE_BYTES = DEFAULT_MAX_SIZE_BYTES
PRODUCT_IMAGE_PURPOSE = "product_image"

CONCEPT_FIELDS = (
    "name",
    "description",
    "category_id",
    "niche_id",
    "price_minor",
    "cost_minor",
    "currency",
    "image_file_id",
)

CONCEPT_STATUSES = frozenset(
    {"draft", "evaluated", "selected", "archived"}
)

CONCEPT_SORT_KEYS = frozenset({"score", "category", "created_at"})

_SORT_ALIASES = {
    "score": "score",
    "latest_score": "score",
    "category": "category",
    "category_id": "category",
    "created": "created_at",
    "created_at": "created_at",
    "date": "created_at",
}


class ConceptError(Exception):
    """Base class for product concept contract failures."""


class ConceptValidationError(ConceptError):
    """Raised when concept fields or an image fail validation."""

    def __init__(self, fields: Mapping[str, str]) -> None:
        self.fields = dict(fields)
        super().__init__("Request validation failed.")


class ConceptNotFound(ConceptError):
    """Raised when a concept does not belong to the active tenant."""


class ConceptConflict(ConceptError):
    """Raised when a concept is no longer editable."""


@dataclass(frozen=True, slots=True)
class UploadedImage:
    """Image bytes received from a multipart request."""

    filename: str
    content_type: str
    data: bytes


def _iso(value: object) -> str | None:
    return value.isoformat() if value is not None else None


def _is_missing(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _value(
    payload: Mapping[str, Any],
    existing: Mapping[str, Any] | None,
    field: str,
) -> object:
    if field in payload:
        return payload[field]
    if existing is not None:
        return existing[field]
    return None


def _text(
    value: object,
    field: str,
    errors: dict[str, str],
) -> str | None:
    if _is_missing(value):
        errors[field] = f"{field} is required"
        return None
    if not isinstance(value, str):
        errors[field] = f"{field} must be a string"
        return None
    result = value.strip()
    if not result:
        errors[field] = f"{field} is required"
        return None
    return result


def _integer(
    value: object,
    field: str,
    errors: dict[str, str],
    *,
    minimum: int,
) -> int | None:
    if _is_missing(value):
        errors[field] = f"{field} is required"
        return None
    if isinstance(value, bool):
        errors[field] = f"{field} must be an integer"
        return None
    if isinstance(value, float) and not value.is_integer():
        errors[field] = f"{field} must be an integer"
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        errors[field] = f"{field} must be an integer"
        return None
    if result < minimum:
        errors[field] = f"{field} must be at least {minimum}"
        return None
    return result


def _uuid_value(
    value: object,
    field: str,
    errors: dict[str, str],
    *,
    required: bool,
) -> uuid.UUID | None:
    if _is_missing(value):
        if required:
            errors[field] = f"{field} is required"
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        errors[field] = f"{field} must be a valid UUID"
        return None


def _currency(value: object, errors: dict[str, str]) -> str | None:
    if _is_missing(value):
        errors["currency"] = "currency is required"
        return None
    if not isinstance(value, str):
        errors["currency"] = "currency must be a three-letter ISO 4217 code"
        return None
    code = value.strip().upper()
    if len(code) != 3 or not code.isalpha():
        errors["currency"] = "currency must be a three-letter ISO 4217 code"
        return None
    return code


def _check_references(
    session: Session,
    tenant: TenantContext,
    *,
    category_id: uuid.UUID | None,
    niche_id: uuid.UUID | None,
    currency: str | None,
    errors: dict[str, str],
) -> None:
    if category_id is not None and "category_id" not in errors:
        category = session.execute(
            text(
                """
                SELECT id FROM categories
                WHERE id = :id AND is_active
                """
            ),
            {"id": category_id},
        ).first()
        if category is None:
            errors["category_id"] = "category_id must reference an active category"

    if niche_id is not None and "niche_id" not in errors:
        if category_id is None or "category_id" in errors:
            errors["niche_id"] = (
                "niche_id must reference an active niche in the selected category"
            )
        else:
            niche = session.execute(
                text(
                    """
                    SELECT id FROM niches
                    WHERE id = :id
                      AND category_id = :category_id
                      AND is_active
                      AND (store_id IS NULL OR store_id = :store_id)
                    """
                ),
                {
                    "id": niche_id,
                    "category_id": category_id,
                    "store_id": tenant.store_id,
                },
            ).first()
            if niche is None:
                errors["niche_id"] = (
                    "niche_id must reference an active niche in the selected category"
                )

    if currency is not None and "currency" not in errors:
        supported = session.execute(
            text(
                """
                SELECT code FROM currencies
                WHERE code = :code AND is_active
                """
            ),
            {"code": currency},
        ).first()
        if supported is None:
            errors["currency"] = "currency must be a supported ISO 4217 code"


def _validate_fields(
    session: Session,
    tenant: TenantContext,
    payload: Mapping[str, Any],
    *,
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    errors: dict[str, str] = {}

    name = _text(_value(payload, existing, "name"), "name", errors)
    description = _text(
        _value(payload, existing, "description"), "description", errors
    )
    category_id = _uuid_value(
        _value(payload, existing, "category_id"),
        "category_id",
        errors,
        required=True,
    )
    niche_id = _uuid_value(
        _value(payload, existing, "niche_id"),
        "niche_id",
        errors,
        required=False,
    )
    price_minor = _integer(
        _value(payload, existing, "price_minor"),
        "price_minor",
        errors,
        minimum=1,
    )
    cost_minor = _integer(
        _value(payload, existing, "cost_minor"),
        "cost_minor",
        errors,
        minimum=0,
    )
    currency = _currency(_value(payload, existing, "currency"), errors)

    _check_references(
        session,
        tenant,
        category_id=category_id,
        niche_id=niche_id,
        currency=currency,
        errors=errors,
    )
    if errors:
        raise ConceptValidationError(errors)

    price = Money(price_minor, currency)
    cost = Money(cost_minor, currency)
    return {
        "name": name,
        "description": description,
        "category_id": category_id,
        "niche_id": niche_id,
        "price_minor": price.amount_minor,
        "cost_minor": cost.amount_minor,
        "currency": currency,
        "gross_margin_bp": gross_margin_bp(price, cost),
    }


def _validate_image(image: UploadedImage) -> str:
    errors: dict[str, str] = {}
    if _is_missing(image.filename):
        errors["image"] = "image filename is required"
    if not isinstance(image.data, (bytes, bytearray)) or not image.data:
        errors["image"] = "image file is empty"
    elif len(image.data) > MAX_IMAGE_BYTES:
        errors["image"] = (
            f"image must be {MAX_IMAGE_BYTES} bytes or smaller"
        )
    content_type = (image.content_type or "").split(";", 1)[0].strip().lower()
    if content_type not in IMAGE_CONTENT_TYPES:
        errors["image"] = (
            "image must be image/jpeg, image/png, or image/webp"
        )
    if errors:
        raise ConceptValidationError(errors)
    return content_type


def _save_image(
    session: Session,
    tenant: TenantContext,
    image: UploadedImage,
) -> Mapping[str, Any]:
    content_type = _validate_image(image)
    try:
        stored = get_storage().save(
            image.data,
            filename=image.filename,
            content_type=content_type,
            purpose=PRODUCT_IMAGE_PURPOSE,
        )
    except ValueError as exc:
        raise ConceptValidationError({"image": str(exc)}) from exc

    return TenantScopedRepository(session, "stored_files").insert(
        {
            "purpose": PRODUCT_IMAGE_PURPOSE,
            "original_filename": stored.original_filename,
            "mime_type": stored.content_type,
            "size_bytes": stored.size_bytes,
            "checksum_sha256": stored.checksum_sha256,
            "storage_provider": "local",
            "storage_key": stored.key,
            "status": "committed",
            "uploaded_by_user_id": tenant.user_id,
        }
    )


def _resolve_image_file_id(
    session: Session,
    image_file_id: object,
) -> uuid.UUID | None:
    if _is_missing(image_file_id):
        return None
    try:
        value = uuid.UUID(str(image_file_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ConceptValidationError(
            {"image_file_id": "image_file_id must be a valid UUID"}
        ) from exc

    row = TenantScopedRepository(session, "stored_files").get(value)
    if (
        row is None
        or row["purpose"] != PRODUCT_IMAGE_PURPOSE
        or row["status"] == "deleted"
        or row["deleted_at"] is not None
    ):
        raise ConceptValidationError(
            {
                "image_file_id": (
                    "image_file_id must reference a product image in this store"
                )
            }
        )
    return value


def _file_out(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "purpose": row["purpose"],
        "original_filename": row["original_filename"],
        "mime_type": row["mime_type"],
        "size_bytes": row["size_bytes"],
        "checksum_sha256": row["checksum_sha256"],
        "status": row["status"],
    }


def _optional(row: Mapping[str, Any], key: str) -> Any:
    return row[key] if key in row else None


def _concept_out(row: Mapping[str, Any]) -> dict[str, Any]:
    margin_bp = int(row["gross_margin_bp"])
    latest_score = _optional(row, "latest_score")
    latest_evaluation_id = _optional(row, "latest_evaluation_id")
    latest_score_scale = _optional(row, "latest_score_scale")
    latest_evaluated_at = _optional(row, "latest_evaluated_at")
    return {
        "id": str(row["id"]),
        "store_id": str(row["store_id"]),
        "name": row["name"],
        "description": row["description"],
        "category_id": str(row["category_id"]),
        "niche_id": str(row["niche_id"]) if row["niche_id"] else None,
        "price_minor": row["price_minor"],
        "cost_minor": row["cost_minor"],
        "currency": row["currency"].strip(),
        "gross_margin_bp": margin_bp,
        "gross_margin_percent": margin_bp / 100,
        "is_negative_margin": margin_bp < 0,
        "image_file_id": (
            str(row["image_file_id"]) if row["image_file_id"] else None
        ),
        "status": row["status"],
        "version": row["version"],
        "latest_evaluation_id": (
            str(latest_evaluation_id) if latest_evaluation_id else None
        ),
        "latest_score": (
            float(latest_score) if latest_score is not None else None
        ),
        "latest_score_scale": (
            int(latest_score_scale)
            if latest_score_scale is not None
            else None
        ),
        "latest_confidence": _optional(row, "latest_confidence"),
        "latest_is_reliable": _optional(row, "latest_is_reliable"),
        "latest_evaluated_at": _iso(latest_evaluated_at),
        "created_by": str(row["created_by"]),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


def upload_product_image(
    session: Session,
    tenant: TenantContext,
    *,
    filename: str,
    content_type: str,
    data: bytes,
) -> dict[str, Any]:
    """Validate and persist a product image, returning its stored file."""

    row = _save_image(
        session,
        tenant,
        UploadedImage(
            filename=filename,
            content_type=content_type,
            data=data,
        ),
    )
    return _file_out(row)


def create_concept(
    session: Session,
    tenant: TenantContext,
    payload: Mapping[str, Any],
    *,
    image: UploadedImage | None = None,
) -> dict[str, Any]:
    """Create a draft concept with a computed gross margin."""

    values = _validate_fields(session, tenant, payload)
    if image is not None:
        image_file_id = _save_image(session, tenant, image)["id"]
    else:
        image_file_id = _resolve_image_file_id(
            session, payload.get("image_file_id")
        )

    row = ProductConceptRepository(session).insert(
        {
            **values,
            "image_file_id": image_file_id,
            "status": "draft",
            "version": 1,
            "created_by": tenant.user_id,
        }
    )
    return _concept_out(row)


def _coerce_version(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConceptValidationError(
            {"version": "version must be a positive integer"}
        )
    if value < 1:
        raise ConceptValidationError(
            {"version": "version must be a positive integer"}
        )
    return value


def _check_version(
    row: Mapping[str, Any], expected_version: int | None
) -> None:
    if expected_version is not None and row["version"] != expected_version:
        raise ConceptConflict("Concept version is stale")


def _date_bound(
    value: object, field: str, *, end_of_day: bool
) -> datetime | None:
    if _is_missing(value):
        return None
    if isinstance(value, datetime):
        bound = value
    elif isinstance(value, date):
        bound = datetime.combine(
            value, time.max if end_of_day else time.min
        )
    elif isinstance(value, str):
        raw = value.strip()
        try:
            if len(raw) == 10:
                parsed_date = date.fromisoformat(raw)
                bound = datetime.combine(
                    parsed_date, time.max if end_of_day else time.min
                )
            else:
                bound = datetime.fromisoformat(
                    raw.replace("Z", "+00:00")
                )
        except ValueError as exc:
            raise ConceptValidationError(
                {field: f"{field} must be an ISO date or datetime"}
            ) from exc
    else:
        raise ConceptValidationError(
            {field: f"{field} must be an ISO date or datetime"}
        )
    if bound.tzinfo is None:
        bound = bound.replace(tzinfo=timezone.utc)
    return bound


def _sort_key(value: str | None) -> str:
    key = (value or "created_at").strip().lower()
    if key not in _SORT_ALIASES:
        raise ConceptValidationError(
            {"sort": "sort must be score, category, or created_at"}
        )
    return _SORT_ALIASES[key]


def _direction(value: str | None) -> str:
    normalized = (value or "desc").strip().lower()
    if normalized not in {"asc", "desc"}:
        raise ConceptValidationError(
            {"direction": "direction must be asc or desc"}
        )
    return normalized


def list_concepts(
    session: Session,
    tenant: TenantContext,
    *,
    status: str | None = None,
    category_id: uuid.UUID | str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    search: str | None = None,
    sort: str | None = "created_at",
    direction: str | None = "desc",
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List store-owned concepts with lifecycle filters and latest score."""

    normalized_status = None
    if not _is_missing(status):
        normalized_status = str(status).strip().lower()
        if normalized_status not in CONCEPT_STATUSES:
            raise ConceptValidationError(
                {
                    "status": (
                        "status must be draft, evaluated, selected, or archived"
                    )
                }
            )

    category_uuid = None
    if not _is_missing(category_id):
        try:
            category_uuid = uuid.UUID(str(category_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ConceptValidationError(
                {"category_id": "category_id must be a valid UUID"}
            ) from exc

    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ConceptValidationError(
            {"limit": "limit must be an integer between 1 and 1000"}
        )
    if limit < 1 or limit > 1000:
        raise ConceptValidationError(
            {"limit": "limit must be an integer between 1 and 1000"}
        )
    if (
        not isinstance(offset, int)
        or isinstance(offset, bool)
        or offset < 0
    ):
        raise ConceptValidationError(
            {"offset": "offset must be a non-negative integer"}
        )

    from_bound = _date_bound(created_from, "created_from", end_of_day=False)
    to_bound = _date_bound(created_to, "created_to", end_of_day=True)
    if from_bound is not None and to_bound is not None and from_bound > to_bound:
        raise ConceptValidationError(
            {"created_to": "created_to must be on or after created_from"}
        )

    normalized_search = None
    if not _is_missing(search):
        normalized_search = str(search).strip()

    rows = ProductConceptRepository(session).list_filtered(
        status=normalized_status,
        category_id=category_uuid,
        created_from=from_bound,
        created_to=to_bound,
        search=normalized_search,
        sort=_sort_key(sort),
        direction=_direction(direction),
        limit=limit,
        offset=offset,
    )
    return [_concept_out(row) for row in rows]


def get_concept(
    session: Session,
    tenant: TenantContext,
    concept_id: uuid.UUID | str,
) -> dict[str, Any]:
    """Reload a concept owned by the active tenant."""

    row = ProductConceptRepository(session).get_with_latest(concept_id)
    if row is None or row["deleted_at"] is not None:
        raise ConceptNotFound("Product concept not found")
    return _concept_out(row)


def _update_failure(
    repository: ProductConceptRepository,
    concept_id: uuid.UUID | str,
) -> None:
    current = repository.get(concept_id)
    if current is None or current["deleted_at"] is not None:
        raise ConceptNotFound("Product concept not found")
    raise ConceptConflict("Concept version is stale")


def update_concept(
    session: Session,
    tenant: TenantContext,
    concept_id: uuid.UUID | str,
    payload: Mapping[str, Any],
    *,
    image: UploadedImage | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Edit a draft concept with optional optimistic concurrency."""

    if expected_version is not None:
        expected_version = _coerce_version(expected_version)

    recognized = {
        field: value for field, value in payload.items() if field in CONCEPT_FIELDS
    }
    if not recognized and image is None:
        raise ConceptValidationError(
            {"body": "at least one field or image is required"}
        )

    repository = ProductConceptRepository(session)
    existing = repository.get(concept_id)
    if existing is None or existing["deleted_at"] is not None:
        raise ConceptNotFound("Product concept not found")
    _check_version(existing, expected_version)
    if existing["status"] != "draft":
        raise ConceptConflict("Only draft concepts can be edited")

    values = _validate_fields(session, tenant, recognized, existing=existing)
    if image is not None:
        image_file_id = _save_image(session, tenant, image)["id"]
    elif "image_file_id" in recognized:
        image_file_id = _resolve_image_file_id(
            session, recognized.get("image_file_id")
        )
    else:
        image_file_id = existing["image_file_id"]

    row = repository.update_versioned(
        concept_id,
        existing["version"],
        {
            **values,
            "image_file_id": image_file_id,
            "version": existing["version"] + 1,
        },
    )
    if row is None:
        _update_failure(repository, concept_id)
    return _concept_out(repository.get_with_latest(concept_id) or row)


def archive_concept(
    session: Session,
    tenant: TenantContext,
    concept_id: uuid.UUID | str,
    *,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Archive a concept so it can be restored later."""

    if expected_version is not None:
        expected_version = _coerce_version(expected_version)

    repository = ProductConceptRepository(session)
    existing = repository.get(concept_id)
    if existing is None or existing["deleted_at"] is not None:
        raise ConceptNotFound("Product concept not found")
    _check_version(existing, expected_version)
    if existing["status"] == "archived":
        return _concept_out(
            repository.get_with_latest(concept_id) or existing
        )

    row = repository.update_versioned(
        concept_id,
        existing["version"],
        {
            "status": "archived",
            "version": existing["version"] + 1,
        },
    )
    if row is None:
        _update_failure(repository, concept_id)
    return _concept_out(repository.get_with_latest(concept_id) or row)


def unarchive_concept(
    session: Session,
    tenant: TenantContext,
    concept_id: uuid.UUID | str,
    *,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Restore an archived concept to its evaluated or draft state."""

    if expected_version is not None:
        expected_version = _coerce_version(expected_version)

    repository = ProductConceptRepository(session)
    existing = repository.get(concept_id)
    if existing is None or existing["deleted_at"] is not None:
        raise ConceptNotFound("Product concept not found")
    _check_version(existing, expected_version)
    if existing["status"] != "archived":
        raise ConceptConflict("Only archived concepts can be unarchived")

    restored_status = (
        "evaluated" if repository.has_evaluation(concept_id) else "draft"
    )
    row = repository.update_versioned(
        concept_id,
        existing["version"],
        {
            "status": restored_status,
            "version": existing["version"] + 1,
        },
    )
    if row is None:
        _update_failure(repository, concept_id)
    return _concept_out(repository.get_with_latest(concept_id) or row)


def delete_concept(
    session: Session,
    tenant: TenantContext,
    concept_id: uuid.UUID | str,
) -> None:
    """Hard-delete an unevaluated concept; evaluated rows must be archived."""

    repository = ProductConceptRepository(session)
    existing = repository.get(concept_id)
    if existing is None or existing["deleted_at"] is not None:
        raise ConceptNotFound("Product concept not found")
    if repository.has_evaluation(concept_id):
        raise ConceptConflict(
            "Evaluated concepts cannot be hard-deleted; archive instead"
        )
    if not repository.delete(concept_id):
        raise ConceptNotFound("Product concept not found")


__all__ = [
    "CONCEPT_FIELDS",
    "CONCEPT_SORT_KEYS",
    "CONCEPT_STATUSES",
    "MAX_IMAGE_BYTES",
    "ConceptConflict",
    "ConceptError",
    "ConceptNotFound",
    "ConceptValidationError",
    "UploadedImage",
    "archive_concept",
    "create_concept",
    "delete_concept",
    "get_concept",
    "list_concepts",
    "unarchive_concept",
    "update_concept",
    "upload_product_image",
]
