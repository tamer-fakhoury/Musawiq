"""Unit economics and CAC from an investment profile (FR-5.2.3)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.services.demand_estimates import DemandEstimateError, load_profile


class UnitEconomicsError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def calculate(profile: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    price = int(profile["selling_price_minor"])
    cost = int(profile["unit_cost_minor"])
    fulfillment = int(profile["fulfillment_cost_minor"])
    fee_bp = int(profile["payment_fee_bp"])
    fee = round(price * fee_bp / 10000)
    contribution = price - cost - fulfillment - fee

    budget = int(profile["available_budget_minor"])
    break_even = (
        round(budget / contribution, 2) if contribution > 0 else None
    )
    conversions = int(snapshot["tracked_conversions"])
    spend = int(snapshot["spend_minor"])
    cac = round(spend / conversions) if conversions > 0 else None

    formulas = {
        "schema_version": 1,
        "contribution_margin_minor": (
            f"{price} - {cost} - {fulfillment} - "
            f"({price} × {fee_bp}/10000) = {contribution}"
        ),
        "break_even_units": (
            f"{budget} / {contribution} = {break_even}"
            if break_even is not None
            else "undefined for non-positive contribution margin"
        ),
        "cac_minor": (
            f"{spend} / {conversions} = {cac}"
            if cac is not None
            else "undefined without tracked conversions"
        ),
    }
    warnings: list[str] = []
    if contribution <= 0:
        warnings.append(
            "NEGATIVE MARGIN: each sale loses money; break-even is undefined."
        )
    if cac is None:
        warnings.append("CAC is undefined because no conversions were tracked.")

    return {
        "contribution_margin_minor": contribution,
        "break_even_units": break_even,
        "cac_minor": cac,
        "formulas": formulas,
        "is_negative_margin": contribution <= 0,
        "warnings": warnings,
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
        raise UnitEconomicsError(
            "no_snapshot",
            "A result snapshot is required before calculating unit economics.",
            status_code=409,
        )
    return row


def _recommendation(
    session: Session,
    tenant: TenantContext,
    test_id: uuid.UUID,
    profile_id: uuid.UUID,
    payload: Mapping[str, Any],
    result: Mapping[str, Any],
):
    recommendation_id = payload.get("recommendation_id")
    if recommendation_id is not None:
        row = session.execute(
            text(
                "SELECT * FROM investment_recommendations WHERE id = :id "
                "AND store_id = :store_id AND test_id = :test_id"
            ),
            {
                "id": uuid.UUID(str(recommendation_id)),
                "store_id": tenant.store_id,
                "test_id": test_id,
            },
        ).mappings().one_or_none()
        if row is None:
            raise UnitEconomicsError(
                "invalid_recommendation",
                "Investment recommendation not found.",
                status_code=404,
            )
        return row
    current = session.execute(
        text(
            "SELECT * FROM investment_recommendations WHERE store_id = :store_id "
            "AND test_id = :test_id AND is_current ORDER BY version DESC LIMIT 1"
        ),
        {"store_id": tenant.store_id, "test_id": test_id},
    ).mappings().one_or_none()
    if current is not None:
        return current

    version = session.execute(
        text(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM investment_recommendations "
            "WHERE test_id = :test_id"
        ),
        {"test_id": test_id},
    ).scalar_one()
    summary = (
        "Unit economics: contribution "
        f"{result['contribution_margin_minor']} minor units."
    )
    return session.execute(
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
            "profile_id": profile_id,
            "version": version,
            "summary": summary,
            "assumptions": Jsonb(
                {
                    "schema_version": 1,
                    "formulas": result["formulas"],
                }
            ),
            "created_by": tenant.user_id,
        },
    ).mappings().one()


def create_unit_economics(
    session: Session,
    tenant: TenantContext,
    test_id: object,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        profile = load_profile(session, tenant, test_id, payload)
    except DemandEstimateError as exc:
        raise UnitEconomicsError(exc.code, exc.message, exc.status_code) from exc
    snapshot = _snapshot(session, tenant, test_id)
    result = calculate(profile, snapshot)
    recommendation = _recommendation(
        session, tenant, test_id, profile["id"], payload, result
    )
    row = session.execute(
        text(
            """
            INSERT INTO unit_economics (
                store_id, investment_recommendation_id,
                contribution_margin_minor, break_even_units, cac_minor,
                formulas, is_negative_margin
            ) VALUES (
                :store_id, :recommendation_id, :contribution_margin_minor,
                :break_even_units, :cac_minor, :formulas, :is_negative_margin
            )
            RETURNING *
            """
        ),
        {
            "store_id": tenant.store_id,
            "recommendation_id": recommendation["id"],
            "contribution_margin_minor": result["contribution_margin_minor"],
            "break_even_units": result["break_even_units"],
            "cac_minor": result["cac_minor"],
            "formulas": Jsonb(result["formulas"]),
            "is_negative_margin": result["is_negative_margin"],
        },
    ).mappings().one()
    return {
        "id": str(row["id"]),
        "investment_recommendation_id": str(row["investment_recommendation_id"]),
        "profile_id": str(profile["id"]),
        "contribution_margin_minor": row["contribution_margin_minor"],
        "break_even_units": (
            float(row["break_even_units"])
            if row["break_even_units"] is not None
            else None
        ),
        "cac_minor": row["cac_minor"],
        "formulas": row["formulas"],
        "is_negative_margin": row["is_negative_margin"],
        "warnings": result["warnings"],
        "created_at": row["created_at"].isoformat(),
    }


__all__ = [
    "UnitEconomicsError",
    "calculate",
    "create_unit_economics",
]
