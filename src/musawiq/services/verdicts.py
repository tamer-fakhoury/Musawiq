"""Immutable test result snapshots (FR-5.1.1)."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext

CONVERSION_EVENTS = {
    "whatsapp_click": "whatsapp_click",
    "cod_order": "cod_order_submitted",
    "deposit_confirmed": "deposit_confirmed",
}


class SnapshotError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _parse(value: object, name: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise SnapshotError(
            "invalid_period", f"{name} must be an ISO-8601 timestamp."
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _test(session: Session, tenant: TenantContext, test_id: object):
    try:
        test_uuid = uuid.UUID(str(test_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise SnapshotError("invalid_test_id", "test_id must be a UUID.") from exc
    row = session.execute(
        text("SELECT * FROM tests WHERE id = :id AND store_id = :store_id"),
        {"id": test_uuid, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise SnapshotError("not_found", "Test not found.", status_code=404)
    return row


def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def compute_snapshot(
    session: Session,
    tenant: TenantContext,
    test_id: object,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    test = _test(session, tenant, test_id)
    start = _parse(payload.get("period_start"), "period_start")
    end = _parse(payload.get("period_end"), "period_end")
    if start >= end:
        raise SnapshotError("invalid_period", "period_start must be before period_end.")

    warnings: list[str] = []
    metrics = session.execute(
        text(
            """
            SELECT array_agg(id) AS ids, coalesce(sum(spend_minor), 0) AS spend,
                   coalesce(sum(impressions), 0) AS impressions,
                   coalesce(sum(clicks), 0) AS clicks,
                   array_agg(DISTINCT currency) AS currencies,
                   min(period_start) AS covered_start,
                   max(period_end) AS covered_end
            FROM metric_snapshots
            WHERE store_id = :store_id AND test_id = :test_id
              AND period_start < :end AND period_end > :start
            """
        ),
        {
            "store_id": tenant.store_id,
            "test_id": test["id"],
            "start": start,
            "end": end,
        },
    ).mappings().one()
    source_ids = [str(value) for value in (metrics["ids"] or [])]
    if not source_ids:
        warnings.append("metric_snapshots_missing")
    else:
        if metrics["covered_start"] > start or metrics["covered_end"] < end:
            warnings.append("metric_coverage_partial")

    currencies = [value.strip() for value in (metrics["currencies"] or [])]
    campaign_currencies = session.execute(
        text(
            "SELECT DISTINCT currency FROM campaigns "
            "WHERE test_id = :test_id AND store_id = :store_id"
        ),
        {"test_id": test["id"], "store_id": tenant.store_id},
    ).scalars().all()
    currency = test["currency"].strip()
    if len(campaign_currencies) > 1:
        warnings.append("campaign_currency_mismatch")
    elif len(campaign_currencies) == 1:
        currency = campaign_currencies[0].strip()
    if currencies and any(value != currency for value in currencies):
        warnings.append("metric_currency_mismatch")

    conversion_type = CONVERSION_EVENTS.get(test["primary_conversion"])
    tracked_conversions = 0
    if conversion_type is None:
        warnings.append("unsupported_primary_conversion")
    else:
        tracked_conversions = session.execute(
            text(
                """
                SELECT count(*) FROM events
                WHERE store_id = :store_id AND test_id = :test_id
                  AND event_type = :event_type AND NOT is_bot
                  AND occurred_at >= :start AND occurred_at < :end
                """
            ),
            {
                "store_id": tenant.store_id,
                "test_id": test["id"],
                "event_type": conversion_type,
                "start": start,
                "end": end,
            },
        ).scalar_one()
        any_events = session.execute(
            text(
                "SELECT count(*) FROM events "
                "WHERE store_id = :store_id AND test_id = :test_id "
                "AND occurred_at >= :start AND occurred_at < :end"
            ),
            {
                "store_id": tenant.store_id,
                "test_id": test["id"],
                "start": start,
                "end": end,
            },
        ).scalar_one()
        if any_events == 0:
            warnings.append("conversion_events_missing")

    confirmed_deposits = session.execute(
        text(
            """
            SELECT count(*) FROM deposits
            WHERE store_id = :store_id AND test_id = :test_id
              AND status = 'confirmed'
              AND verified_at >= :start AND verified_at < :end
            """
        ),
        {
            "store_id": tenant.store_id,
            "test_id": test["id"],
            "start": start,
            "end": end,
        },
    ).scalar_one()
    if test["primary_conversion"] == "deposit_confirmed":
        any_deposits = session.execute(
            text(
                "SELECT count(*) FROM deposits "
                "WHERE store_id = :store_id AND test_id = :test_id "
                "AND verified_at >= :start AND verified_at < :end"
            ),
            {
                "store_id": tenant.store_id,
                "test_id": test["id"],
                "start": start,
                "end": end,
            },
        ).scalar_one()
        if any_deposits == 0:
            warnings.append("confirmed_deposits_source_missing")

    required = ["metric_snapshots", "conversion_events"]
    available = 0
    if source_ids:
        available += 1
    if "conversion_events_missing" not in warnings:
        available += 1
    if test["primary_conversion"] == "deposit_confirmed":
        required.append("confirmed_deposits")
        if "confirmed_deposits_source_missing" not in warnings:
            available += 1
    if "unsupported_primary_conversion" in warnings:
        available = max(0, available - 1)
    completeness = round(available / len(required), 4)

    clicks = int(metrics["clicks"])
    spend = int(metrics["spend"])
    conversion_rate = (
        round(tracked_conversions / clicks, 6) if clicks > 0 else None
    )
    cpc = round(spend / tracked_conversions) if tracked_conversions > 0 else None

    row = session.execute(
        text(
            """
            INSERT INTO test_result_snapshots (
                store_id, test_id, period_start, period_end, currency,
                spend_minor, impressions, clicks, tracked_conversions,
                confirmed_deposits, conversion_rate, cost_per_conversion_minor,
                data_completeness, source_metric_snapshot_ids, captured_at
            ) VALUES (
                :store_id, :test_id, :period_start, :period_end, :currency,
                :spend_minor, :impressions, :clicks, :tracked_conversions,
                :confirmed_deposits, :conversion_rate,
                :cost_per_conversion_minor, :data_completeness,
                CAST(:source_ids AS uuid[]), :captured_at
            )
            RETURNING *
            """
        ),
        {
            "store_id": tenant.store_id,
            "test_id": test["id"],
            "period_start": start,
            "period_end": end,
            "currency": currency,
            "spend_minor": spend,
            "impressions": int(metrics["impressions"]),
            "clicks": clicks,
            "tracked_conversions": tracked_conversions,
            "confirmed_deposits": confirmed_deposits,
            "conversion_rate": conversion_rate,
            "cost_per_conversion_minor": cpc,
            "data_completeness": completeness,
            "source_ids": source_ids,
            "captured_at": dt.datetime.now(dt.timezone.utc),
        },
    ).mappings().one()
    return {
        "id": str(row["id"]),
        "test_id": str(row["test_id"]),
        "period_start": _iso(row["period_start"]),
        "period_end": _iso(row["period_end"]),
        "currency": row["currency"].strip(),
        "spend_minor": row["spend_minor"],
        "impressions": row["impressions"],
        "clicks": row["clicks"],
        "tracked_conversions": row["tracked_conversions"],
        "confirmed_deposits": row["confirmed_deposits"],
        "conversion_rate": (
            float(row["conversion_rate"])
            if row["conversion_rate"] is not None
            else None
        ),
        "cost_per_conversion_minor": row["cost_per_conversion_minor"],
        "data_completeness": float(row["data_completeness"]),
        "source_metric_snapshot_ids": [
            str(value) for value in row["source_metric_snapshot_ids"]
        ],
        "captured_at": _iso(row["captured_at"]),
        "warnings": warnings,
    }


__all__ = ["CONVERSION_EVENTS", "SnapshotError", "compute_snapshot"]
