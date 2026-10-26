"""Audience profile versioning and segment replacement."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext

MIN_AGE = 0
MAX_AGE = 120


class AudienceError(Exception):
    """Base class for audience contract failures."""


class AudienceValidationError(AudienceError):
    """Raised when a profile or segment payload is invalid."""


class AudienceNotFound(AudienceError):
    """Raised when the profile does not belong to the active tenant."""


def _coerce_uuid(value: object) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AudienceValidationError("niche_ids must contain valid UUIDs") from exc


def _uuid_list(value: object, name: str) -> list[uuid.UUID]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise AudienceValidationError(f"{name} must be a list")
    return [_coerce_uuid(item) for item in value]


def _text_list(value: object, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise AudienceValidationError(f"{name} must be a list")
    if not all(isinstance(item, str) for item in value):
        raise AudienceValidationError(f"{name} must contain only strings")
    return list(value)


def _notes(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AudienceValidationError("notes must be a string")
    return value


def _iso(value: object) -> str | None:
    return value.isoformat() if value is not None else None


def _profile_out(
    row: Mapping[str, Any],
    segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "version": row["version"],
        "status": row["status"],
        "is_current": row["is_current"],
        "niche_ids": [str(item) for item in row["niche_ids"]],
        "languages": list(row["languages"]),
        "notes": row["notes"],
        "created_by": str(row["created_by"]),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
        "segments": segments or [],
    }


def _segment_out(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "audience_profile_id": str(row["audience_profile_id"]),
        "label": row["label"],
        "locations": row["locations"],
        "age_min": row["age_min"],
        "age_max": row["age_max"],
        "genders": list(row["genders"]),
        "interests": list(row["interests"]),
        "languages": list(row["languages"]),
        "created_at": _iso(row["created_at"]),
    }


def _fetch_segments(
    session: Session, tenant: TenantContext, profile_id: uuid.UUID
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT * FROM audience_segments
            WHERE store_id = :store_id AND audience_profile_id = :profile_id
            ORDER BY created_at, id
            """
        ),
        {"store_id": tenant.store_id, "profile_id": profile_id},
    ).mappings().all()
    return [_segment_out(row) for row in rows]


def _next_version(session: Session, tenant: TenantContext) -> int:
    return session.execute(
        text(
            """
            SELECT COALESCE(MAX(version), 0) + 1
            FROM audience_profiles
            WHERE store_id = :store_id
            """
        ),
        {"store_id": tenant.store_id},
    ).scalar_one()


def _demote_current(session: Session, tenant: TenantContext) -> None:
    session.execute(
        text(
            """
            UPDATE audience_profiles
            SET is_current = false
            WHERE store_id = :store_id AND is_current
            """
        ),
        {"store_id": tenant.store_id},
    )


def _insert_profile(
    session: Session,
    tenant: TenantContext,
    *,
    version: int,
    niche_ids: list[uuid.UUID],
    languages: list[str],
    notes: str | None,
) -> Mapping[str, Any]:
    return session.execute(
        text(
            """
            INSERT INTO audience_profiles (
                store_id, version, status, is_current, niche_ids,
                languages, notes, created_by
            ) VALUES (
                :store_id, :version, 'active', true,
                CAST(:niche_ids AS uuid[]), CAST(:languages AS text[]),
                :notes, :created_by
            )
            RETURNING *
            """
        ),
        {
            "store_id": tenant.store_id,
            "version": version,
            "niche_ids": niche_ids,
            "languages": languages,
            "notes": notes,
            "created_by": tenant.user_id,
        },
    ).mappings().one()


def create_profile(
    session: Session, tenant: TenantContext, payload: Mapping[str, Any]
) -> dict[str, Any]:
    niche_ids = _uuid_list(payload.get("niche_ids"), "niche_ids")
    if not niche_ids:
        raise AudienceValidationError("at least one niche is required")
    languages = _text_list(payload.get("languages"), "languages")
    notes = _notes(payload.get("notes"))

    version = _next_version(session, tenant)
    _demote_current(session, tenant)
    row = _insert_profile(
        session,
        tenant,
        version=version,
        niche_ids=niche_ids,
        languages=languages,
        notes=notes,
    )
    return _profile_out(row, [])


def get_current(
    session: Session, tenant: TenantContext
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT * FROM audience_profiles
            WHERE store_id = :store_id AND is_current
            LIMIT 1
            """
        ),
        {"store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        return None
    return _profile_out(row, _fetch_segments(session, tenant, row["id"]))


def _validated_segment(segment: object) -> dict[str, Any]:
    if not isinstance(segment, Mapping):
        raise AudienceValidationError("each segment must be an object")

    label = segment.get("label", "")
    if not isinstance(label, str):
        raise AudienceValidationError("segment label must be a string")

    age_min = segment.get("age_min")
    age_max = segment.get("age_max")
    if (
        not isinstance(age_min, int)
        or isinstance(age_min, bool)
        or not isinstance(age_max, int)
        or isinstance(age_max, bool)
    ):
        raise AudienceValidationError("segment age_min and age_max must be integers")
    if age_min < MIN_AGE:
        raise AudienceValidationError("segment age_min must be at least 0")
    if age_max > MAX_AGE:
        raise AudienceValidationError("segment age_max must be at most 120")
    if age_min > age_max:
        raise AudienceValidationError("segment age_min must not exceed age_max")

    locations = segment.get("locations", [])
    if not isinstance(locations, list):
        raise AudienceValidationError("segment locations must be a list")

    return {
        "label": label,
        "locations": locations,
        "age_min": age_min,
        "age_max": age_max,
        "genders": _text_list(segment.get("genders"), "genders"),
        "interests": _text_list(segment.get("interests"), "interests"),
        "languages": _text_list(segment.get("languages"), "languages"),
    }


def replace_segments(
    session: Session,
    tenant: TenantContext,
    profile_id: uuid.UUID | str,
    segments: object,
) -> list[dict[str, Any]]:
    if not isinstance(segments, list):
        raise AudienceValidationError("segments must be a list")
    validated = [_validated_segment(segment) for segment in segments]

    profile_uuid = _coerce_uuid(profile_id)
    exists = session.execute(
        text(
            """
            SELECT id FROM audience_profiles
            WHERE id = :id AND store_id = :store_id
            FOR UPDATE
            """
        ),
        {"id": profile_uuid, "store_id": tenant.store_id},
    ).first()
    if exists is None:
        raise AudienceNotFound("Audience profile not found")

    session.execute(
        text(
            """
            DELETE FROM audience_segments
            WHERE store_id = :store_id AND audience_profile_id = :profile_id
            """
        ),
        {"store_id": tenant.store_id, "profile_id": profile_uuid},
    )

    inserted: list[dict[str, Any]] = []
    for segment in validated:
        row = session.execute(
            text(
                """
                INSERT INTO audience_segments (
                    store_id, audience_profile_id, label, locations,
                    age_min, age_max, genders, interests, languages
                ) VALUES (
                    :store_id, :profile_id, :label, :locations,
                    :age_min, :age_max, CAST(:genders AS text[]),
                    CAST(:interests AS text[]), CAST(:languages AS text[])
                )
                RETURNING *
                """
            ),
            {
                "store_id": tenant.store_id,
                "profile_id": profile_uuid,
                "label": segment["label"],
                "locations": Jsonb(segment["locations"]),
                "age_min": segment["age_min"],
                "age_max": segment["age_max"],
                "genders": segment["genders"],
                "interests": segment["interests"],
                "languages": segment["languages"],
            },
        ).mappings().one()
        inserted.append(_segment_out(row))
    return inserted


def update_profile(
    session: Session,
    tenant: TenantContext,
    profile_id: uuid.UUID | str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    profile_uuid = _coerce_uuid(profile_id)
    source = session.execute(
        text(
            """
            SELECT * FROM audience_profiles
            WHERE id = :id AND store_id = :store_id
            LIMIT 1
            """
        ),
        {"id": profile_uuid, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if source is None:
        raise AudienceNotFound("Audience profile not found")

    if "niche_ids" in payload:
        niche_ids = _uuid_list(payload.get("niche_ids"), "niche_ids")
        if not niche_ids:
            raise AudienceValidationError("at least one niche is required")
    else:
        niche_ids = list(source["niche_ids"])

    if "languages" in payload:
        languages = _text_list(payload.get("languages"), "languages")
    else:
        languages = list(source["languages"])

    if "notes" in payload:
        notes = _notes(payload.get("notes"))
    else:
        notes = source["notes"]

    version = _next_version(session, tenant)
    _demote_current(session, tenant)
    row = _insert_profile(
        session,
        tenant,
        version=version,
        niche_ids=niche_ids,
        languages=languages,
        notes=notes,
    )
    return _profile_out(row, [])


__all__ = [
    "AudienceError",
    "AudienceNotFound",
    "AudienceValidationError",
    "create_profile",
    "get_current",
    "replace_segments",
    "update_profile",
]
