"""Versioned investment recalculation (FR-5.2.6)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.services.demand_estimates import (
    DemandEstimateError,
    estimate as estimate_demand,
    load_profile,
)
from musawiq.services.unit_economics import calculate as calculate_economics

DIFF_FIELDS = (
    "repeat_rate",
    "seasonality_factor",
    "attribution_adjustment",
    "traffic_source",
    "selling_price_minor",
    "unit_cost_minor",
    "fulfillment_cost_minor",
    "payment_fee_bp",
    "available_budget_minor",
)


class InvestmentError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _snapshot(session: Session, tenant: TenantContext, test_id):
    row = session.execute(
        text(
            "SELECT * FROM test_result_snapshots WHERE store_id = :store_id "
            "AND test_id = :test_id ORDER BY captured_at DESC, id DESC LIMIT 1"
        ),
        {"store_id": tenant.store_id, "test_id": test_id},
    ).mappings().one_or_none()
    if row is None:
        raise InvestmentError(
            "no_snapshot",
            "A result snapshot is required before recalculating.",
            status_code=409,
        )
    return row


def _profile(
    session: Session, tenant: TenantContext, test_id, payload: Mapping[str, Any]
):
    profile = payload.get("profile")
    if not profile:
        try:
            return load_profile(session, tenant, test_id, payload)
        except DemandEstimateError as exc:
            raise InvestmentError(exc.code, exc.message, exc.status_code) from exc

    version = session.execute(
        text(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM investment_profiles "
            "WHERE test_id = :test_id"
        ),
        {"test_id": test_id},
    ).scalar_one()
    session.execute(
        text(
            "UPDATE investment_profiles SET is_current = false "
            "WHERE test_id = :test_id AND is_current"
        ),
        {"test_id": test_id},
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
                :store_id, :test_id, :version, :unit_cost_minor,
                :selling_price_minor, :fulfillment_cost_minor, :payment_fee_bp,
                :available_budget_minor, :target_margin_bp, :supplier_moq,
                :lead_time_days, :currency, true, :created_by
            )
            RETURNING *
            """
        ),
        {
            "store_id": tenant.store_id,
            "test_id": test_id,
            "version": version,
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


def _risk(value: float) -> str:
    if value >= 0.66:
        return "high"
    if value >= 0.33:
        return "medium"
    return "low"


def _scenarios(profile: Mapping[str, Any], demand: Mapping[str, Any]):
    price = int(profile["selling_price_minor"])
    cost = int(profile["unit_cost_minor"])
    fulfillment = int(profile["fulfillment_cost_minor"])
    fee_bp = int(profile["payment_fee_bp"])
    low, base, high = (
        int(demand["low_units"]),
        int(demand["base_units"]),
        int(demand["high_units"]),
    )
    rows = []
    for label, quantity in (
        ("conservative", max(low, 1)),
        ("base", max(base, 1)),
        ("aggressive", max(high, 1)),
    ):
        sold_low = min(quantity, low)
        sold_high = min(quantity, high)
        inventory = quantity * cost
        revenue_low = sold_low * price
        revenue_high = sold_high * price
        fee_low = round(revenue_low * fee_bp / 10000)
        fee_high = round(revenue_high * fee_bp / 10000)
        profit_low = revenue_low - inventory - fulfillment * sold_low - fee_low
        profit_high = (
            revenue_high - inventory - fulfillment * sold_high - fee_high
        )
        overstock = _risk(max(0.0, (quantity - high) / max(high, 1)))
        stockout = _risk(max(0.0, (low - quantity) / max(low, 1)))
        feasible = quantity >= int(profile["supplier_moq"])
        rows.append(
            {
                "label": label,
                "quantity": quantity,
                "inventory_cost_minor": inventory,
                "expected_units_sold_low": sold_low,
                "expected_units_sold_high": sold_high,
                "revenue_low_minor": revenue_low,
                "revenue_high_minor": revenue_high,
                "profit_low_minor": profit_low,
                "profit_high_minor": profit_high,
                "sell_through_low": round(sold_low / quantity, 4),
                "sell_through_high": round(sold_high / quantity, 4),
                "overstock_risk": overstock,
                "stockout_risk": stockout,
                "is_feasible": feasible,
                "infeasibility_reason": (
                    None
                    if feasible
                    else f"quantity below supplier MOQ {profile['supplier_moq']}"
                ),
            }
        )
    return rows


def _changes(prior: Mapping[str, Any] | None, current: Mapping[str, Any]):
    if prior is None:
        return {"previous_version": None, "changed": []}
    changed = []
    for field in DIFF_FIELDS:
        before = (prior.get("inputs") or {}).get(field)
        after = (current.get("inputs") or {}).get(field)
        if before != after:
            changed.append({"field": field, "before": before, "after": after})
    return {"previous_version": prior.get("version"), "changed": changed}


def _current(session: Session, tenant: TenantContext, test_id):
    return session.execute(
        text(
            "SELECT * FROM investment_recommendations WHERE store_id = :store_id "
            "AND test_id = :test_id AND is_current ORDER BY version DESC LIMIT 1"
        ),
        {"store_id": tenant.store_id, "test_id": test_id},
    ).mappings().one_or_none()


def _recommendation_out(row: Mapping[str, Any]) -> dict[str, Any]:
    assumptions = row["assumptions_snapshot"] or {}
    return {
        "id": str(row["id"]),
        "test_id": str(row["test_id"]),
        "investment_profile_id": str(row["investment_profile_id"]),
        "version": row["version"],
        "summary": row["summary"],
        "assumptions_snapshot": assumptions,
        "is_current": row["is_current"],
        "created_at": row["created_at"].isoformat(),
        "demand_estimate": assumptions.get("demand"),
        "unit_economics": assumptions.get("economics"),
        "quantity_scenarios": assumptions.get("scenarios"),
    }


def recalculate(
    session: Session,
    tenant: TenantContext,
    test_id: object,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot = _snapshot(session, tenant, test_id)
    profile = _profile(session, tenant, test_id, payload)
    assumptions = payload.get("assumptions") or {}
    try:
        demand = estimate_demand(snapshot, profile, assumptions)
    except DemandEstimateError as exc:
        raise InvestmentError(exc.code, exc.message, exc.status_code) from exc
    economics = calculate_economics(profile, snapshot)
    scenarios = _scenarios(profile, demand)

    prior_row = _current(session, tenant, test_id)
    prior = (
        {
            "version": prior_row["version"],
            "inputs": (prior_row["assumptions_snapshot"] or {}).get("inputs", {}),
        }
        if prior_row is not None
        else None
    )

    inputs = {
        "selling_price_minor": int(profile["selling_price_minor"]),
        "unit_cost_minor": int(profile["unit_cost_minor"]),
        "fulfillment_cost_minor": int(profile["fulfillment_cost_minor"]),
        "payment_fee_bp": int(profile["payment_fee_bp"]),
        "available_budget_minor": int(profile["available_budget_minor"]),
        **{
            key: demand["assumptions"][key]["value"]
            for key in (
                "repeat_rate",
                "seasonality_factor",
                "attribution_adjustment",
                "traffic_source",
            )
        },
    }
    assumptions_snapshot = {
        "schema_version": 1,
        "inputs": inputs,
        "assumptions": demand["assumptions"],
        "demand": demand,
        "economics": economics,
        "scenarios": scenarios,
    }
    changes = _changes(prior, {"version": None, "inputs": inputs})

    version = (
        int(prior_row["version"]) + 1 if prior_row is not None else 1
    )
    session.execute(
        text(
            "UPDATE investment_recommendations SET is_current = false "
            "WHERE test_id = :test_id AND is_current"
        ),
        {"test_id": test_id},
    )
    recommendation = session.execute(
        text(
            """
            INSERT INTO investment_recommendations (
                store_id, test_id, investment_profile_id, version, summary,
                assumptions_snapshot, is_current, created_by
            ) VALUES (
                :store_id, :test_id, :profile_id, :version, :summary,
                :assumptions, true, :created_by
            )
            RETURNING *
            """
        ),
        {
            "store_id": tenant.store_id,
            "test_id": test_id,
            "profile_id": profile["id"],
            "version": version,
            "summary": (
                f"Demand {demand['low_units']}-{demand['high_units']} units; "
                f"contribution {economics['contribution_margin_minor']}."
            ),
            "assumptions": Jsonb(assumptions_snapshot),
            "created_by": tenant.user_id,
        },
    ).mappings().one()
    recommendation_id = recommendation["id"]

    session.execute(
        text(
            """
            INSERT INTO demand_estimates (
                store_id, investment_recommendation_id, low_units, base_units,
                high_units, assumptions, confidence
            ) VALUES (
                :store_id, :recommendation_id, :low, :base, :high,
                :assumptions, :confidence
            )
            """
        ),
        {
            "store_id": tenant.store_id,
            "recommendation_id": recommendation_id,
            "low": demand["low_units"],
            "base": demand["base_units"],
            "high": demand["high_units"],
            "assumptions": Jsonb(demand["assumptions"]),
            "confidence": demand["confidence"],
        },
    )
    session.execute(
        text(
            """
            INSERT INTO unit_economics (
                store_id, investment_recommendation_id,
                contribution_margin_minor, break_even_units, cac_minor,
                formulas, is_negative_margin
            ) VALUES (
                :store_id, :recommendation_id, :margin, :break_even, :cac,
                :formulas, :negative
            )
            """
        ),
        {
            "store_id": tenant.store_id,
            "recommendation_id": recommendation_id,
            "margin": economics["contribution_margin_minor"],
            "break_even": economics["break_even_units"],
            "cac": economics["cac_minor"],
            "formulas": Jsonb(economics["formulas"]),
            "negative": economics["is_negative_margin"],
        },
    )
    for scenario in scenarios:
        session.execute(
            text(
                """
                INSERT INTO quantity_scenarios (
                    store_id, investment_recommendation_id, label, quantity,
                    inventory_cost_minor, expected_units_sold_low,
                    expected_units_sold_high, revenue_low_minor,
                    revenue_high_minor, profit_low_minor, profit_high_minor,
                    sell_through_low, sell_through_high, overstock_risk,
                    stockout_risk, is_feasible, infeasibility_reason
                ) VALUES (
                    :store_id, :recommendation_id, :label, :quantity,
                    :inventory_cost_minor, :expected_units_sold_low,
                    :expected_units_sold_high, :revenue_low_minor,
                    :revenue_high_minor, :profit_low_minor, :profit_high_minor,
                    :sell_through_low, :sell_through_high, :overstock_risk,
                    :stockout_risk, :is_feasible, :infeasibility_reason
                )
                """
            ),
            {
                "store_id": tenant.store_id,
                "recommendation_id": recommendation_id,
                **scenario,
            },
        )

    out = _recommendation_out(recommendation)
    out["changes"] = changes
    return out


def history(
    session: Session, tenant: TenantContext, test_id: object
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            "SELECT * FROM investment_recommendations WHERE store_id = :store_id "
            "AND test_id = :test_id ORDER BY version DESC"
        ),
        {"store_id": tenant.store_id, "test_id": test_id},
    ).mappings().all()
    return [_recommendation_out(row) for row in rows]


def current(
    session: Session, tenant: TenantContext, test_id: object
) -> dict[str, Any] | None:
    row = _current(session, tenant, test_id)
    if row is None:
        return None
    return _recommendation_out(row)


__all__ = [
    "DIFF_FIELDS",
    "InvestmentError",
    "current",
    "history",
    "recalculate",
]
