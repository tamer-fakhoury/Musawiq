"""Data sufficiency assessment for product concepts.

Policy version 1:

- Sales history uses confirmed and fulfilled orders only. It is ``missing``
  when there are no qualifying orders, ``stale`` when the latest order is older
  than ``sales_history_stale_days``, ``insufficient`` when the store has fewer
  than ``sales_history_min_orders`` orders or the history spans fewer than
  ``sales_history_min_days`` days, and ``available`` otherwise.
- Audience data requires a current active profile with at least one niche, at
  least one segment, and every segment must contain at least one location. It
  is ``stale`` when the profile was updated more than ``audience_stale_days``
  ago.
- Cost and price are ``missing`` only when unavailable and ``insufficient``
  when price is not positive or cost is negative.
- Competitive data is optional. It is ``missing`` unless supplied by the
  caller, and it never blocks scoring.
- Any critical input that is not ``available`` makes the overall status
  ``insufficient`` and adds the exact input name to ``blocking_reasons``.
  Missing critical inputs are never imputed.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy.orm import Session

from musawiq.config import Settings, get_settings
from musawiq.db.tenant import TenantContext
from musawiq.repositories.audience_profiles import (
    AudienceProfileRepository,
    AudienceSnapshot,
)
from musawiq.repositories.orders import OrderRepository, SalesHistorySummary
from musawiq.repositories.product_concepts import ProductConceptRepository
from musawiq.repositories.sufficiency_checks import SufficiencyCheckRepository
from musawiq.services.concepts import ConceptNotFound

AVAILABLE = "available"
MISSING = "missing"
STALE = "stale"
INSUFFICIENT = "insufficient"
SUFFICIENT = "sufficient"

CRITICAL_INPUTS = ("sales_history", "audience", "cost_price")


@dataclass(frozen=True, slots=True)
class SufficiencyPolicy:
    """Versioned thresholds used by the sufficiency engine."""

    version: str
    sales_min_orders: int
    sales_min_history_days: int
    sales_stale_after_days: int
    audience_stale_after_days: int
    competitive_stale_after_days: int

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "SufficiencyPolicy":
        source = settings or get_settings()
        return cls(
            version=source.sufficiency_policy_version,
            sales_min_orders=source.sales_history_min_orders,
            sales_min_history_days=source.sales_history_min_days,
            sales_stale_after_days=source.sales_history_stale_days,
            audience_stale_after_days=source.audience_stale_days,
            competitive_stale_after_days=source.competitive_data_stale_days,
        )


def _iso(value: object) -> str | None:
    return value.isoformat() if value is not None else None


def _days_since(now: datetime, value: datetime) -> float:
    return (now - value).total_seconds() / 86400


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def _sales_history_status(
    summary: SalesHistorySummary,
    policy: SufficiencyPolicy,
    now: datetime,
) -> str:
    if summary.order_count == 0 or summary.last_placed_at is None:
        return MISSING
    if summary.first_placed_at is None:
        return MISSING
    if _days_since(now, summary.last_placed_at) > policy.sales_stale_after_days:
        return STALE
    if summary.order_count < policy.sales_min_orders:
        return INSUFFICIENT
    span_days = _days_since(
        summary.last_placed_at, summary.first_placed_at
    )
    if span_days < policy.sales_min_history_days:
        return INSUFFICIENT
    return AVAILABLE


def _audience_status(
    snapshot: AudienceSnapshot,
    policy: SufficiencyPolicy,
    now: datetime,
) -> str:
    profile = snapshot.profile
    if profile is None:
        return MISSING
    if profile["status"] != "active":
        return INSUFFICIENT
    updated_at = profile["updated_at"]
    if isinstance(updated_at, datetime) and (
        _days_since(now, updated_at) > policy.audience_stale_after_days
    ):
        return STALE
    if not profile["niche_ids"]:
        return INSUFFICIENT
    if not snapshot.segments:
        return INSUFFICIENT
    for segment in snapshot.segments:
        locations = segment["locations"]
        if not isinstance(locations, list) or not locations:
            return INSUFFICIENT
    return AVAILABLE


def _cost_price_status(concept: Mapping[str, Any]) -> str:
    price = concept["price_minor"]
    cost = concept["cost_minor"]
    if price is None or cost is None:
        return MISSING
    if int(price) <= 0 or int(cost) < 0:
        return INSUFFICIENT
    return AVAILABLE


def _competitive_data_status(
    competitive_data: Mapping[str, Any] | None,
    policy: SufficiencyPolicy,
    now: datetime,
) -> str:
    if competitive_data is None:
        return MISSING
    observed_at = _as_datetime(competitive_data.get("observed_at"))
    if observed_at is None:
        return MISSING
    if _days_since(now, observed_at) > policy.competitive_stale_after_days:
        return STALE
    items = competitive_data.get("items")
    if items is None:
        items = competitive_data.get("item_count")
    if isinstance(items, int) and not isinstance(items, bool):
        count = items
    elif isinstance(items, (list, tuple)):
        count = len(items)
    else:
        count = 0
    return INSUFFICIENT if count < 1 else AVAILABLE


def _check_out(
    row: Mapping[str, Any], policy: SufficiencyPolicy | None = None
) -> dict[str, Any]:
    blocking = row["blocking_reasons"]
    if not isinstance(blocking, list):
        blocking = []
    return {
        "id": str(row["id"]),
        "store_id": str(row["store_id"]),
        "product_concept_id": str(row["product_concept_id"]),
        "sales_history_status": row["sales_history_status"],
        "audience_status": row["audience_status"],
        "cost_price_status": row["cost_price_status"],
        "competitive_data_status": row["competitive_data_status"],
        "overall_status": row["overall_status"],
        "blocking_reasons": blocking,
        "checked_at": _iso(row["checked_at"]),
        "created_at": _iso(row["created_at"]),
        "policy_version": policy.version if policy is not None else None,
    }


def run_sufficiency_check(
    session: Session,
    tenant: TenantContext,
    concept_id: uuid.UUID | str,
    *,
    policy: SufficiencyPolicy | None = None,
    competitive_data: Mapping[str, Any] | None = None,
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    """Assess every sufficiency input and persist the result."""

    active_policy = policy or SufficiencyPolicy.from_settings()
    try:
        concept = ProductConceptRepository(session).get(concept_id)
    except ValueError as exc:
        raise ConceptNotFound("Product concept not found") from exc
    if concept is None or concept["deleted_at"] is not None:
        raise ConceptNotFound("Product concept not found")

    now = checked_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    statuses = {
        "sales_history": _sales_history_status(
            OrderRepository(session).sales_history(),
            active_policy,
            now,
        ),
        "audience": _audience_status(
            AudienceProfileRepository(session).current_with_segments(),
            active_policy,
            now,
        ),
        "cost_price": _cost_price_status(concept),
        "competitive_data": _competitive_data_status(
            competitive_data,
            active_policy,
            now,
        ),
    }
    blocking_reasons = [
        name for name in CRITICAL_INPUTS if statuses[name] != AVAILABLE
    ]
    overall_status = (
        SUFFICIENT if not blocking_reasons else INSUFFICIENT
    )

    row = SufficiencyCheckRepository(session).insert_check(
        {
            "product_concept_id": concept["id"],
            "sales_history_status": statuses["sales_history"],
            "audience_status": statuses["audience"],
            "cost_price_status": statuses["cost_price"],
            "competitive_data_status": statuses["competitive_data"],
            "overall_status": overall_status,
            "blocking_reasons": Jsonb(blocking_reasons),
            "checked_at": now,
        }
    )
    return _check_out(row, active_policy)


def get_latest_sufficiency_check(
    session: Session,
    tenant: TenantContext,
    concept_id: uuid.UUID | str,
) -> dict[str, Any] | None:
    """Return the most recent stored check for a concept."""

    try:
        row = SufficiencyCheckRepository(session).latest_for_concept(
            concept_id
        )
    except ValueError as exc:
        raise ConceptNotFound("Product concept not found") from exc
    if row is None:
        return None
    return _check_out(row, SufficiencyPolicy.from_settings())


__all__ = [
    "AVAILABLE",
    "CRITICAL_INPUTS",
    "INSUFFICIENT",
    "MISSING",
    "STALE",
    "SUFFICIENT",
    "SufficiencyPolicy",
    "get_latest_sufficiency_check",
    "run_sufficiency_check",
]
