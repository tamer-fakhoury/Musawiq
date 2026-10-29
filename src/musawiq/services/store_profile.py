"""Store profile: selected categories and niches, plus custom niches."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext

MAX_NICHE_NAME_LENGTH = 60


class StoreProfileError(Exception):
    """Base class for store profile contract failures."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _uuid_list(value: object, name: str) -> list[uuid.UUID]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise StoreProfileError(f"invalid_{name}", f"{name} must be a list of UUIDs")
    seen: list[uuid.UUID] = []
    for item in value:
        try:
            parsed = uuid.UUID(str(item))
        except (TypeError, ValueError, AttributeError) as exc:
            raise StoreProfileError(
                f"invalid_{name}", f"{name} must contain valid UUIDs"
            ) from exc
        if parsed not in seen:
            seen.append(parsed)
    return seen


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[: MAX_NICHE_NAME_LENGTH] or "niche"


def _profile_from(settings: Mapping[str, Any]) -> dict[str, Any]:
    profile = settings.get("profile") or {}
    return {
        "category_ids": [str(v) for v in profile.get("category_ids", [])],
        "niche_ids": [str(v) for v in profile.get("niche_ids", [])],
    }


def get_store_profile(session: Session, tenant: TenantContext) -> dict[str, Any]:
    row = session.execute(
        text("SELECT settings FROM stores WHERE id = :id"),
        {"id": tenant.store_id},
    ).scalar_one()
    return _profile_from(row or {})


def update_store_profile(
    session: Session,
    tenant: TenantContext,
    *,
    category_ids: object,
    niche_ids: object,
) -> dict[str, Any]:
    categories = _uuid_list(category_ids, "category_ids")
    if not categories:
        raise StoreProfileError(
            "category_required", "At least one category is required."
        )
    niches = _uuid_list(niche_ids, "niche_ids")

    active_categories = session.execute(
        text(
            "SELECT count(*) FROM categories "
            "WHERE id = ANY(:ids) AND is_active"
        ),
        {"ids": categories},
    ).scalar_one()
    if active_categories != len(categories):
        raise StoreProfileError(
            "invalid_category", "Every category must exist and be active."
        )

    if niches:
        valid_niches = session.execute(
            text(
                """
                SELECT count(*) FROM niches
                WHERE id = ANY(:ids)
                  AND is_active
                  AND category_id = ANY(:categories)
                  AND (store_id IS NULL OR store_id = :store_id)
                """
            ),
            {
                "ids": niches,
                "categories": categories,
                "store_id": tenant.store_id,
            },
        ).scalar_one()
        if valid_niches != len(niches):
            raise StoreProfileError(
                "invalid_niche",
                "Every niche must exist, be active, and match a selected category.",
            )

    profile = {
        "category_ids": [str(v) for v in categories],
        "niche_ids": [str(v) for v in niches],
    }
    session.execute(
        text(
            """
            UPDATE stores
            SET settings = jsonb_set(
                    coalesce(settings, '{}'::jsonb),
                    '{profile}',
                    :profile,
                    true
                ) || '{"schema_version": 1}'::jsonb
            WHERE id = :id
            """
        ),
        {
            "id": tenant.store_id,
            "profile": Jsonb(profile),
        },
    )
    return profile


def create_custom_niche(
    session: Session,
    tenant: TenantContext,
    *,
    category_id: uuid.UUID,
    name: object,
) -> dict[str, Any]:
    if not isinstance(name, str) or not name.strip():
        raise StoreProfileError("invalid_niche_name", "Niche name is required.")
    clean_name = name.strip()
    if len(clean_name) > MAX_NICHE_NAME_LENGTH:
        raise StoreProfileError(
            "niche_name_too_long",
            f"Niche name must be {MAX_NICHE_NAME_LENGTH} characters or fewer.",
        )

    exists = session.execute(
        text("SELECT 1 FROM categories WHERE id = :id AND is_active"),
        {"id": category_id},
    ).scalar_one_or_none()
    if exists is None:
        raise StoreProfileError(
            "invalid_category", "Category must exist and be active."
        )

    slug = _slugify(clean_name)
    taken = session.execute(
        text(
            "SELECT 1 FROM niches WHERE store_id = :store_id AND slug = :slug"
        ),
        {"store_id": tenant.store_id, "slug": slug},
    ).scalar_one_or_none()
    if taken is not None:
        raise StoreProfileError(
            "niche_exists", "A niche with this name already exists.", status_code=409
        )

    row = session.execute(
        text(
            """
            INSERT INTO niches (
                store_id, category_id, name, slug, is_active
            )
            VALUES (:store_id, :category_id, :name, :slug, true)
            RETURNING id, category_id, store_id, name, slug
            """
        ),
        {
            "store_id": tenant.store_id,
            "category_id": category_id,
            "name": clean_name,
            "slug": slug,
        },
    ).mappings().one()
    return {
        "id": str(row["id"]),
        "category_id": str(row["category_id"]),
        "store_id": str(row["store_id"]),
        "name": row["name"],
        "slug": row["slug"],
    }


__all__ = [
    "MAX_NICHE_NAME_LENGTH",
    "StoreProfileError",
    "create_custom_niche",
    "get_store_profile",
    "update_store_profile",
]
