"""Demand estimation with explicit assumptions (FR-5.2.2)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext

PROFILE_FIELDS = (
    "unit_cost_minor",
    "selling_price_minor",
    "available_budget_minor",
    "target_margin_bp",
    "supplier_moq",
    "lead_time_days",
)
DEFAULT_ASSUMPTIONS = {
    "repeat_rate": 0.1,
    "seasonality_factor": 1.0,
    "attribution_adjustment": 0.9,
    "traffic_source": "test_campaign",
}
LOW_FACTOR = 0.7
HIGH_FACTOR = 1.3


class DemandEstimateError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _assumption(value: object, name: str, default: float, *, is_rate: bool):
    if value is None:
        value = default
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DemandEstimateError(
            "invalid_assumption", f"{name} must be numeric."
        )
    number = float(value)
    if is_rate and not 0 <= number <= 1:
        raise DemandEstimateError(
            "invalid_assumption", f"{name} must be between 0 and 1."
        )
    if not is_rate and number <= 0:
        raise DemandEstimateError(
            "invalid_assumption", f"{name} must be positive."
        )
    return number


def estimate(
    snapshot: Mapping[str, Any],
    profile: Mapping[str, Any],
    assumptions_input: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    overrides = dict(assumptions_input or {})
    repeat_rate = _assumption(
        overrides.get("repeat_rate"), "repeat_rate", DEFAULT_ASSUMPTIONS["repeat_rate"], is_rate=True
    )
    seasonality = _assumption(
        overrides.get("seasonality_factor"),
        "seasonality_factor",
        DEFAULT_ASSUMPTIONS["seasonality_factor"],
        is_rate=False,
    )
    attribution = _assumption(
        overrides.get("attribution_adjustment"),
        "attribution_adjustment",
        DEFAULT_ASSUMPTIONS["attribution_adjustment"],
        is_rate=True,
    )
    traffic_source = str(
        overrides.get("traffic_source") or DEFAULT_ASSUMPTIONS["traffic_source"]
    )

    conversions = int(
        snapshot["tracked_conversions"] or snapshot["confirmed_deposits"] or 0
    )
    factor = (1 + repeat_rate) * seasonality * attribution
    base = max(0, round(conversions * factor))
    low = max(0, round(base * LOW_FACTOR))
    high = max(0, round(base * HIGH_FACTOR))
    if low > base:
        low = base
    if high < base:
        high = base

    completeness = float(snapshot["data_completeness"])
    clicks = int(snapshot["clicks"])
    if completeness >= 1.0 and clicks >= 1000:
        confidence = "high"
    elif completeness >= 0.8 and clicks >= 300:
        confidence = "medium"
    else:
        confidence = "low"

    limitations: list[str] = ["Demand is a range, not a single-point forecast."]
    if completeness < 1.0:
        limitations.append(
            f"Snapshot data completeness is {completeness}; source coverage is partial."
        )
    if clicks < 300:
        limitations.append(
            f"Small sample size ({clicks} clicks) reduces confidence."
        )
    if conversions == 0:
        limitations.append("No tracked conversions were observed in the window.")

    assumptions = {
        "schema_version": 1,
        "traffic_source": {
            "value": traffic_source,
            "source": "test_campaign",
        },
        "repeat_rate": {
            "value": repeat_rate,
            "source": "merchant_input" if "repeat_rate" in overrides else "default",
        },
        "seasonality_factor": {
            "value": seasonality,
            "source": (
                "merchant_input"
                if "seasonality_factor" in overrides
                else "default"
            ),
        },
        "attribution_adjustment": {
            "value": attribution,
            "source": (
                "merchant_input"
                if "attribution_adjustment" in overrides
                else "default"
            ),
        },
        "limitations": limitations,
    }
    return {
        "low_units": low,
        "base_units": base,
        "high_units": high,
        "confidence": confidence,
        "assumptions": assumptions,
    }


def _snapshot(session: Session, tenant: TenantContext, test_id):
    row = session.execute(
        text(
            "SELECT * FROM test_result_snapshots WHERE store_id = :store_id "
            "AND test_id = :test_id ORDER BY captured_at DESC, id DESC LIMIT 1"
        ),
        {"store_id": tenant.store_id, "test_id": test_id},
    ).mappings().one_or_none()
    if row is None:
        raise DemandEstimateError(
            "no_snapshot",
            "A result snapshot is required before estimating demand.",
            status_code=409,
        )
    return row


def _profile(
    session: Session,
    tenant: TenantContext,
    test_id,
    payload: Mapping[str, Any],
):
    profile_id = payload.get("profile_id")
    if profile_id is not None:
        row = session.execute(
            text(
                "SELECT * FROM investment_profiles WHERE id = :id "
                "AND store_id = :store_id AND test_id = :test_id"
            ),
            {
                "id": uuid.UUID(str(profile_id)),
                "store_id": tenant.store_id,
                "test_id": test_id,
            },
        ).mappings().one_or_none()
        if row is None:
            raise DemandEstimateError(
                "invalid_profile", "Investment profile not found.", status_code=404
            )
        return row

    current = session.execute(
        text(
            "SELECT * FROM investment_profiles WHERE store_id = :store_id "
            "AND test_id = :test_id AND is_current ORDER BY version DESC LIMIT 1"
        ),
        {"store_id": tenant.store_id, "test_id": test_id},
    ).mappings().one_or_none()
    if current is not None:
        return current

    profile = payload.get("profile") or {}
    missing = [field for field in PROFILE_FIELDS if profile.get(field) is None]
    if missing:
        raise DemandEstimateError(
            "profile_required",
            "Provide profile_id or an investment profile: "
            + ", ".join(missing),
            status_code=409,
        )
    return session.execute(
        text(
            """
            INSERT INTO investment_profiles (
                store_id, test_id, version, unit_cost_minor,
                selling_price_minor, fulfillment_cost_minor, payment_fee_bp,
                available_budget_minor, target_margin_bp, supplier_moq,
                lead_time_days, currency, is_current, created_by
            ) VALUES (
                :store_id, :test_id, 1, :unit_cost_minor, :selling_price_minor,
                :fulfillment_cost_minor, :payment_fee_bp,
                :available_budget_minor, :target_margin_bp, :supplier_moq,
                :lead_time_days, :currency, true, :created_by
            )
            RETURNING *
            """
        ),
        {
            "store_id": tenant.store_id,
            "test_id": test_id,
            "unit_cost_minor": profile["unit_cost_minor"],
            "selling_price_minor": profile["selling_price_minor"],
            "fulfillment_cost_minor": profile.get("fulfillment_cost_minor", 0),
            "payment_fee_bp": profile.get("payment_fee_bp", 0),
            "available_budget_minor": profile["available_budget_minor"],
            "target_margin_bp": profile["target_margin_bp"],
            "supplier_moq": profile["supplier_moq"],
            "lead_time_days": profile["lead_time_days"],
            "currency": profile.get("currency", "USD"),
            "created_by": tenant.user_id,
        },
    ).mappings().one()


def create_demand_estimate(
    session: Session,
    tenant: TenantContext,
    test_id: object,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot = _snapshot(session, tenant, test_id)
    profile = _profile(session, tenant, test_id, payload)
    result = estimate(snapshot, profile, payload.get("assumptions"))

    version = session.execute(
        text(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM investment_recommendations "
            "WHERE test_id = :test_id"
        ),
        {"test_id": test_id},
    ).scalar_one()
    session.execute(
        text(
            "UPDATE investment_recommendations SET is_current = false "
            "WHERE test_id = :test_id AND is_current"
        ),
        {"test_id": test_id},
    )
    summary = (
        f"Estimated demand range {result['low_units']}-{result['high_units']} "
        f"units (base {result['base_units']}) with {result['confidence']} confidence."
    )
    recommendation_id = session.execute(
        text(
            """
            INSERT INTO investment_recommendations (
                store_id, test_id, investment_profile_id, version, summary,
                assumptions_snapshot, is_current, created_by
            ) VALUES (
                :store_id, :test_id, :profile_id, :version, :summary,
                :assumptions, true, :created_by
            )
            RETURNING id
            """
        ),
        {
            "store_id": tenant.store_id,
            "test_id": test_id,
            "profile_id": profile["id"],
            "version": version,
            "summary": summary,
            "assumptions": Jsonb(result["assumptions"]),
            "created_by": tenant.user_id,
        },
    ).scalar_one()
    row = session.execute(
        text(
            """
            INSERT INTO demand_estimates (
                store_id, investment_recommendation_id, low_units, base_units,
                high_units, assumptions, confidence
            ) VALUES (
                :store_id, :recommendation_id, :low_units, :base_units,
                :high_units, :assumptions, :confidence
            )
            RETURNING *
            """
        ),
        {
            "store_id": tenant.store_id,
            "recommendation_id": recommendation_id,
            "low_units": result["low_units"],
            "base_units": result["base_units"],
            "high_units": result["high_units"],
            "assumptions": Jsonb(result["assumptions"]),
            "confidence": result["confidence"],
        },
    ).mappings().one()
    return {
        "id": str(row["id"]),
        "investment_recommendation_id": str(recommendation_id),
        "profile_id": str(profile["id"]),
        "low_units": row["low_units"],
        "base_units": row["base_units"],
        "high_units": row["high_units"],
        "confidence": row["confidence"],
        "assumptions": row["assumptions"],
        "limitations": result["assumptions"]["limitations"],
        "created_at": row["created_at"].isoformat(),
    }


__all__ = [
    "DEFAULT_ASSUMPTIONS",
    "DemandEstimateError",
    "create_demand_estimate",
    "estimate",
]
