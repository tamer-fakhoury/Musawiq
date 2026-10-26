"""Campaign, ad set, and ad variation setup and manual edits."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext

BUDGET_TYPES = frozenset({"daily", "total"})
CAMPAIGN_STATUS_TRANSITIONS = {"draft": "active", "active": "paused"}
VARIATION_STATUSES = frozenset({"draft", "approved", "discarded"})


class CampaignError(Exception):
    """Base class for campaign contract failures."""


class CampaignValidationError(CampaignError):
    """Raised when a campaign payload is invalid."""


class CampaignNotFound(CampaignError):
    """Raised when a record does not belong to the active tenant."""


def _coerce_uuid(value: object, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise CampaignValidationError(f"{name} must be a valid UUID") from exc


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CampaignValidationError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_text(value: object, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CampaignValidationError(f"{name} must be a string")
    return value


def _positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise CampaignValidationError(f"{name} must be greater than zero")
    return value


def _iso(value: object) -> str | None:
    return value.isoformat() if value is not None else None


def _campaign_out(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "test_id": str(row["test_id"]),
        "provider": row["provider"],
        "name": row["name"],
        "objective": row["objective"],
        "status": row["status"],
        "budget_type": row["budget_type"],
        "budget_minor": row["budget_minor"],
        "currency": row["currency"].strip(),
        "start_at": _iso(row["start_at"]),
        "end_at": _iso(row["end_at"]),
        "created_by": str(row["created_by"]),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


def _adset_out(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "campaign_id": str(row["campaign_id"]),
        "name": row["name"],
        "status": row["status"],
        "targeting": row["targeting"],
        "budget_type": row["budget_type"],
        "budget_minor": row["budget_minor"],
        "currency": row["currency"].strip(),
        "start_at": _iso(row["start_at"]),
        "end_at": _iso(row["end_at"]),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


def _variation_out(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "adset_id": str(row["adset_id"]),
        "name": row["name"],
        "copy_text": row["copy_text"],
        "headline": row["headline"],
        "description": row["description"],
        "post_id": str(row["post_id"]) if row["post_id"] else None,
        "destination_url": row["destination_url"],
        "status": row["status"],
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


def _campaign_row(
    session: Session, tenant: TenantContext, campaign_id: uuid.UUID | str
) -> Mapping[str, Any]:
    campaign_uuid = _coerce_uuid(campaign_id, "campaign_id")
    row = session.execute(
        text(
            """
            SELECT * FROM campaigns
            WHERE id = :id AND store_id = :store_id
            LIMIT 1
            """
        ),
        {"id": campaign_uuid, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise CampaignNotFound("Campaign not found")
    return row


def _reference_exists(
    session: Session, table: str, column: str, value: object
) -> bool:
    if table not in {"ad_platforms", "currencies"}:
        raise ValueError("unsupported reference table")
    if column not in {"code"}:
        raise ValueError("unsupported reference column")
    return session.execute(
        text(f"SELECT 1 FROM {table} WHERE {column} = :value"),
        {"value": value},
    ).first() is not None


def _validate_targeting(targeting: object) -> dict[str, Any]:
    if not isinstance(targeting, Mapping):
        raise CampaignValidationError("targeting must be an object")
    value = dict(targeting)
    for key in ("locations", "genders", "interests", "languages"):
        if key in value and not isinstance(value[key], list):
            raise CampaignValidationError(f"targeting.{key} must be a list")
    age_min = value.get("age_min")
    age_max = value.get("age_max")
    if (age_min is None) != (age_max is None):
        raise CampaignValidationError(
            "targeting.age_min and targeting.age_max must be provided together"
        )
    if age_min is not None:
        if (
            not isinstance(age_min, int)
            or isinstance(age_min, bool)
            or not isinstance(age_max, int)
            or isinstance(age_max, bool)
        ):
            raise CampaignValidationError(
                "targeting.age_min and targeting.age_max must be integers"
            )
        if age_min > age_max:
            raise CampaignValidationError(
                "targeting.age_min must not exceed targeting.age_max"
            )
    return value


def create_campaign(
    session: Session, tenant: TenantContext, payload: Mapping[str, Any]
) -> dict[str, Any]:
    test_id = payload.get("test_id")
    if test_id is None:
        raise CampaignValidationError(
            "test_id is required by the current schema"
        )
    test_uuid = _coerce_uuid(test_id, "test_id")
    test_exists = session.execute(
        text(
            """
            SELECT 1 FROM tests
            WHERE id = :id AND store_id = :store_id
            """
        ),
        {"id": test_uuid, "store_id": tenant.store_id},
    ).first()
    if test_exists is None:
        raise CampaignValidationError("test_id is not valid for this store")

    provider = _required_text(payload.get("provider"), "provider")
    if not _reference_exists(session, "ad_platforms", "code", provider):
        raise CampaignValidationError("provider must come from ad_platforms")

    name = _required_text(payload.get("name"), "name")
    objective = _required_text(payload.get("objective"), "objective")

    budget_type = payload.get("budget_type")
    if budget_type not in BUDGET_TYPES:
        raise CampaignValidationError("budget_type must be daily or total")
    budget_minor = _positive_int(payload.get("budget_minor"), "budget_minor")

    currency = _required_text(payload.get("currency"), "currency").upper()
    if len(currency) != 3 or not _reference_exists(
        session, "currencies", "code", currency
    ):
        raise CampaignValidationError("currency must be a known ISO 4217 code")

    start_at = payload.get("start_at")
    end_at = payload.get("end_at")
    if start_at is None or end_at is None:
        raise CampaignValidationError("start_at and end_at are required")
    if start_at >= end_at:
        raise CampaignValidationError("start_at must be before end_at")

    row = session.execute(
        text(
            """
            INSERT INTO campaigns (
                store_id, test_id, provider, name, objective, status,
                budget_type, budget_minor, currency, start_at, end_at,
                created_by
            ) VALUES (
                :store_id, :test_id, :provider, :name, :objective, 'draft',
                :budget_type, :budget_minor, :currency, :start_at, :end_at,
                :created_by
            )
            RETURNING *
            """
        ),
        {
            "store_id": tenant.store_id,
            "test_id": test_uuid,
            "provider": provider,
            "name": name,
            "objective": objective,
            "budget_type": budget_type,
            "budget_minor": budget_minor,
            "currency": currency,
            "start_at": start_at,
            "end_at": end_at,
            "created_by": tenant.user_id,
        },
    ).mappings().one()
    return _campaign_out(row)


def create_adset(
    session: Session,
    tenant: TenantContext,
    campaign_id: uuid.UUID | str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    campaign = _campaign_row(session, tenant, campaign_id)
    campaign_uuid = campaign["id"]

    name = _required_text(payload.get("name"), "name")
    targeting = _validate_targeting(payload.get("targeting"))

    budget_type = payload.get("budget_type")
    if budget_type is not None and budget_type not in BUDGET_TYPES:
        raise CampaignValidationError("budget_type must be daily or total")
    budget_minor = payload.get("budget_minor")
    if budget_minor is not None:
        budget_minor = _positive_int(budget_minor, "budget_minor")
        if budget_type is None:
            budget_type = campaign["budget_type"]

    currency = payload.get("currency")
    if currency is None:
        currency = campaign["currency"]
    else:
        currency = _required_text(currency, "currency").upper()
        if len(currency) != 3 or not _reference_exists(
            session, "currencies", "code", currency
        ):
            raise CampaignValidationError(
                "currency must be a known ISO 4217 code"
            )

    start_at = payload.get("start_at") or campaign["start_at"]
    end_at = payload.get("end_at") or campaign["end_at"]
    if start_at >= end_at:
        raise CampaignValidationError("start_at must be before end_at")

    row = session.execute(
        text(
            """
            INSERT INTO ad_sets (
                store_id, campaign_id, name, status, targeting,
                budget_type, budget_minor, currency, start_at, end_at
            ) VALUES (
                :store_id, :campaign_id, :name, 'draft', :targeting,
                :budget_type, :budget_minor, :currency, :start_at, :end_at
            )
            RETURNING *
            """
        ),
        {
            "store_id": tenant.store_id,
            "campaign_id": campaign_uuid,
            "name": name,
            "targeting": Jsonb(targeting),
            "budget_type": budget_type,
            "budget_minor": budget_minor,
            "currency": currency,
            "start_at": start_at,
            "end_at": end_at,
        },
    ).mappings().one()
    return _adset_out(row)


def create_variation(
    session: Session,
    tenant: TenantContext,
    campaign_id: uuid.UUID | str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    campaign = _campaign_row(session, tenant, campaign_id)

    adset_id = payload.get("adset_id")
    if adset_id is None:
        raise CampaignValidationError("adset_id is required")
    adset_uuid = _coerce_uuid(adset_id, "adset_id")
    adset_exists = session.execute(
        text(
            """
            SELECT 1 FROM ad_sets
            WHERE id = :id AND campaign_id = :campaign_id
              AND store_id = :store_id
            """
        ),
        {
            "id": adset_uuid,
            "campaign_id": campaign["id"],
            "store_id": tenant.store_id,
        },
    ).first()
    if adset_exists is None:
        raise CampaignNotFound("Ad set not found")

    copy_text = _required_text(payload.get("copy_text"), "copy_text")
    headline = _optional_text(payload.get("headline"), "headline")
    description = _optional_text(payload.get("description"), "description")

    post_id = payload.get("post_id")
    destination_url = payload.get("destination_url")
    if post_id is None and not destination_url:
        raise CampaignValidationError(
            "post_id or destination_url is required"
        )
    post_uuid = None
    if post_id is not None:
        post_uuid = _coerce_uuid(post_id, "post_id")
        post_exists = session.execute(
            text(
                "SELECT 1 FROM posts WHERE id = :id AND store_id = :store_id"
            ),
            {"id": post_uuid, "store_id": tenant.store_id},
        ).first()
        if post_exists is None:
            raise CampaignValidationError("post_id is not valid for this store")
    if destination_url is not None:
        destination_url = _required_text(destination_url, "destination_url")

    row = session.execute(
        text(
            """
            INSERT INTO ad_variations (
                store_id, adset_id, copy_text, headline, description,
                post_id, destination_url, status
            ) VALUES (
                :store_id, :adset_id, :copy_text, :headline, :description,
                :post_id, :destination_url, 'draft'
            )
            RETURNING *
            """
        ),
        {
            "store_id": tenant.store_id,
            "adset_id": adset_uuid,
            "copy_text": copy_text,
            "headline": headline,
            "description": description,
            "post_id": post_uuid,
            "destination_url": destination_url,
        },
    ).mappings().one()
    return _variation_out(row)


def update_campaign(
    session: Session,
    tenant: TenantContext,
    campaign_id: uuid.UUID | str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    campaign = _campaign_row(session, tenant, campaign_id)

    name = campaign["name"]
    if "name" in payload:
        name = _required_text(payload.get("name"), "name")

    budget_type = campaign["budget_type"]
    if "budget_type" in payload:
        budget_type = payload.get("budget_type")
        if budget_type not in BUDGET_TYPES:
            raise CampaignValidationError("budget_type must be daily or total")

    budget_minor = campaign["budget_minor"]
    if "budget_minor" in payload:
        budget_minor = _positive_int(
            payload.get("budget_minor"), "budget_minor"
        )

    start_at = campaign["start_at"]
    if "start_at" in payload:
        if payload.get("start_at") is None:
            raise CampaignValidationError("start_at cannot be null")
        start_at = payload["start_at"]
    end_at = campaign["end_at"]
    if "end_at" in payload:
        if payload.get("end_at") is None:
            raise CampaignValidationError("end_at cannot be null")
        end_at = payload["end_at"]
    if start_at >= end_at:
        raise CampaignValidationError("start_at must be before end_at")

    status = campaign["status"]
    if "status" in payload:
        requested = payload.get("status")
        if requested != status:
            if CAMPAIGN_STATUS_TRANSITIONS.get(status) != requested:
                raise CampaignValidationError(
                    "campaign status can only move draft -> active -> paused"
                )
            status = requested

    row = session.execute(
        text(
            """
            UPDATE campaigns
            SET name = :name,
                budget_type = :budget_type,
                budget_minor = :budget_minor,
                start_at = :start_at,
                end_at = :end_at,
                status = :status
            WHERE id = :id AND store_id = :store_id
            RETURNING *
            """
        ),
        {
            "id": campaign["id"],
            "store_id": tenant.store_id,
            "name": name,
            "budget_type": budget_type,
            "budget_minor": budget_minor,
            "start_at": start_at,
            "end_at": end_at,
            "status": status,
        },
    ).mappings().one()
    return _campaign_out(row)


def update_variation(
    session: Session,
    tenant: TenantContext,
    variation_id: uuid.UUID | str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    variation_uuid = _coerce_uuid(variation_id, "variation_id")
    row = session.execute(
        text(
            """
            SELECT * FROM ad_variations
            WHERE id = :id AND store_id = :store_id
            LIMIT 1
            """
        ),
        {"id": variation_uuid, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise CampaignNotFound("Ad variation not found")

    assignments: list[str] = []
    params: dict[str, Any] = {
        "id": variation_uuid,
        "store_id": tenant.store_id,
    }

    if "copy_text" in payload:
        assignments.append("copy_text = :copy_text")
        params["copy_text"] = _required_text(
            payload.get("copy_text"), "copy_text"
        )
    if "headline" in payload:
        assignments.append("headline = :headline")
        params["headline"] = _optional_text(
            payload.get("headline"), "headline"
        )
    if "description" in payload:
        assignments.append("description = :description")
        params["description"] = _optional_text(
            payload.get("description"), "description"
        )
    if "status" in payload:
        status = payload.get("status")
        if status not in VARIATION_STATUSES:
            raise CampaignValidationError(
                "status must be draft, approved, or discarded"
            )
        assignments.append("status = :status")
        params["status"] = status

    if not assignments:
        return _variation_out(row)

    updated = session.execute(
        text(
            "UPDATE ad_variations SET "
            + ", ".join(assignments)
            + " WHERE id = :id AND store_id = :store_id RETURNING *"
        ),
        params,
    ).mappings().one()
    return _variation_out(updated)


def list_campaigns(
    session: Session, tenant: TenantContext
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT * FROM campaigns
            WHERE store_id = :store_id
            ORDER BY created_at DESC, id
            """
        ),
        {"store_id": tenant.store_id},
    ).mappings().all()
    return [_campaign_out(row) for row in rows]


def get_campaign(
    session: Session,
    tenant: TenantContext,
    campaign_id: uuid.UUID | str,
) -> dict[str, Any]:
    campaign = _campaign_row(session, tenant, campaign_id)
    campaign_uuid = campaign["id"]

    adsets = session.execute(
        text(
            """
            SELECT * FROM ad_sets
            WHERE campaign_id = :campaign_id AND store_id = :store_id
            ORDER BY created_at, id
            """
        ),
        {"campaign_id": campaign_uuid, "store_id": tenant.store_id},
    ).mappings().all()

    variations = session.execute(
        text(
            """
            SELECT v.* FROM ad_variations v
            JOIN ad_sets s ON s.id = v.adset_id
            WHERE s.campaign_id = :campaign_id
              AND s.store_id = :store_id
              AND v.store_id = :store_id
            ORDER BY v.created_at, v.id
            """
        ),
        {"campaign_id": campaign_uuid, "store_id": tenant.store_id},
    ).mappings().all()

    by_adset: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for variation in variations:
        by_adset.setdefault(variation["adset_id"], []).append(
            _variation_out(variation)
        )

    result = _campaign_out(campaign)
    result["ad_sets"] = [
        {
            **_adset_out(adset),
            "variations": by_adset.get(adset["id"], []),
        }
        for adset in adsets
    ]
    return result


def config_fingerprint(
    session: Session,
    tenant: TenantContext,
    campaign_id: uuid.UUID | str,
) -> str:
    campaign = _campaign_row(session, tenant, campaign_id)
    campaign_uuid = campaign["id"]

    adsets = session.execute(
        text(
            """
            SELECT targeting FROM ad_sets
            WHERE campaign_id = :campaign_id AND store_id = :store_id
            ORDER BY created_at, id
            """
        ),
        {"campaign_id": campaign_uuid, "store_id": tenant.store_id},
    ).mappings().all()

    copy_texts = session.execute(
        text(
            """
            SELECT v.copy_text FROM ad_variations v
            JOIN ad_sets s ON s.id = v.adset_id
            WHERE s.campaign_id = :campaign_id
              AND s.store_id = :store_id
              AND v.store_id = :store_id
            ORDER BY v.created_at, v.id
            """
        ),
        {"campaign_id": campaign_uuid, "store_id": tenant.store_id},
    ).scalars().all()

    payload = {
        "provider": campaign["provider"],
        "objective": campaign["objective"],
        "budget_type": campaign["budget_type"],
        "budget_minor": campaign["budget_minor"],
        "currency": campaign["currency"].strip(),
        "start_at": campaign["start_at"].isoformat(),
        "end_at": campaign["end_at"].isoformat(),
        "targeting": [adset["targeting"] for adset in adsets],
        "copy_texts": list(copy_texts),
    }
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


__all__ = [
    "CampaignError",
    "CampaignNotFound",
    "CampaignValidationError",
    "config_fingerprint",
    "create_adset",
    "create_campaign",
    "create_variation",
    "get_campaign",
    "list_campaigns",
    "update_campaign",
    "update_variation",
]
