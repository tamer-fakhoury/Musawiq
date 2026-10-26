"""Campaign signal ingestion and retrieval."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext


class SignalValidationError(Exception):
    """Raised when a signal window or row is invalid."""


def _ctr(clicks: int, impressions: int) -> Decimal | None:
    if impressions == 0:
        return None
    return Decimal(clicks) / Decimal(impressions)


def _cpc(spend_minor: int, clicks: int) -> int | None:
    return round(spend_minor / clicks) if clicks else None


def _cpm(spend_minor: int, impressions: int) -> int | None:
    return (
        round(spend_minor * 1000 / impressions)
        if impressions
        else None
    )


def _cost_per_conversion(
    spend_minor: int, conversions: int | None
) -> int | None:
    return round(spend_minor / conversions) if conversions else None


def _validate_counts(row: Mapping[str, Any]) -> None:
    for key in ("impressions", "reach", "clicks", "spend_minor"):
        value = row[key]
        if value < 0:
            raise SignalValidationError(f"{key} must be non-negative")
    for key in ("conversions", "engagement"):
        value = row.get(key)
        if value is not None and value < 0:
            raise SignalValidationError(f"{key} must be non-negative")
    if row["reach"] > row["impressions"]:
        raise SignalValidationError("reach must not exceed impressions")


def _validate_references(
    session: Session,
    tenant: TenantContext,
    campaign_id: uuid.UUID,
    rows: list[Mapping[str, Any]],
) -> None:
    for row in rows:
        adset_id = row.get("adset_id")
        if adset_id is not None:
            found = session.execute(
                text(
                    """
                    SELECT 1 FROM ad_sets
                    WHERE id = :id AND campaign_id = :campaign_id
                      AND store_id = :store_id
                    """
                ),
                {
                    "id": adset_id,
                    "campaign_id": campaign_id,
                    "store_id": tenant.store_id,
                },
            ).first()
            if found is None:
                raise SignalValidationError(
                    "adset_id does not belong to this campaign"
                )

        variation_id = row.get("ad_variation_id")
        if variation_id is not None:
            found = session.execute(
                text(
                    """
                    SELECT 1 FROM ad_variations v
                    JOIN ad_sets s ON s.id = v.adset_id
                    WHERE v.id = :id
                      AND s.campaign_id = :campaign_id
                      AND v.store_id = :store_id
                      AND s.store_id = :store_id
                    """
                ),
                {
                    "id": variation_id,
                    "campaign_id": campaign_id,
                    "store_id": tenant.store_id,
                },
            ).first()
            if found is None:
                raise SignalValidationError(
                    "ad_variation_id does not belong to this campaign"
                )


def _raw(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: str(value) if isinstance(value, uuid.UUID) else value
        for key, value in row.items()
    }


def write_signals(
    session: Session,
    tenant: TenantContext,
    campaign: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    period_start = payload["period_start"]
    period_end = payload["period_end"]
    if period_end <= period_start:
        raise SignalValidationError(
            "period_end must be after period_start"
        )

    rows = list(payload.get("rows") or [])
    for row in rows:
        _validate_counts(row)
    _validate_references(session, tenant, campaign["id"], rows)

    campaign_id = campaign["id"]
    test_id = campaign["test_id"]
    currency = campaign["currency"].strip()

    for row in rows:
        conversions = row.get("conversions")
        session.execute(
            text(
                """
                INSERT INTO metric_snapshots (
                    store_id, test_id, provider, campaign_id, adset_id,
                    ad_variation_id, period_start, period_end, snapshot_at,
                    currency, spend_minor, impressions, reach, clicks, ctr,
                    cpc_minor, cpm_minor, engagement, platform_conversions,
                    cost_per_conversion_minor, raw
                )
                VALUES (
                    :store_id, :test_id, :provider, :campaign_id, :adset_id,
                    :ad_variation_id, :period_start, :period_end, now(),
                    :currency, :spend_minor, :impressions, :reach, :clicks,
                    :ctr, :cpc_minor, :cpm_minor, :engagement,
                    :platform_conversions, :cost_per_conversion_minor, :raw
                )
                ON CONFLICT (
                    campaign_id, adset_id, ad_variation_id,
                    period_start, period_end
                )
                DO UPDATE SET
                    provider = EXCLUDED.provider,
                    snapshot_at = EXCLUDED.snapshot_at,
                    currency = EXCLUDED.currency,
                    spend_minor = EXCLUDED.spend_minor,
                    impressions = EXCLUDED.impressions,
                    reach = EXCLUDED.reach,
                    clicks = EXCLUDED.clicks,
                    ctr = EXCLUDED.ctr,
                    cpc_minor = EXCLUDED.cpc_minor,
                    cpm_minor = EXCLUDED.cpm_minor,
                    engagement = EXCLUDED.engagement,
                    platform_conversions = EXCLUDED.platform_conversions,
                    cost_per_conversion_minor = EXCLUDED.cost_per_conversion_minor,
                    raw = EXCLUDED.raw
                """
            ),
            {
                "store_id": tenant.store_id,
                "test_id": test_id,
                "provider": payload["provider"],
                "campaign_id": campaign_id,
                "adset_id": row.get("adset_id"),
                "ad_variation_id": row.get("ad_variation_id"),
                "period_start": period_start,
                "period_end": period_end,
                "currency": currency,
                "spend_minor": row["spend_minor"],
                "impressions": row["impressions"],
                "reach": row["reach"],
                "clicks": row["clicks"],
                "ctr": _ctr(row["clicks"], row["impressions"]),
                "cpc_minor": _cpc(row["spend_minor"], row["clicks"]),
                "cpm_minor": _cpm(row["spend_minor"], row["impressions"]),
                "engagement": row.get("engagement"),
                "platform_conversions": conversions,
                "cost_per_conversion_minor": _cost_per_conversion(
                    row["spend_minor"], conversions
                ),
                "raw": Jsonb(_raw(row)),
            },
        )

    return {
        "campaign_id": str(campaign_id),
        "window": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        },
        "rows_written": len(rows),
    }


def list_signals(
    session: Session,
    tenant: TenantContext,
    campaign: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT period_start, period_end, impressions, clicks,
                   spend_minor, ctr, cpc_minor, platform_conversions
            FROM metric_snapshots
            WHERE campaign_id = :campaign_id
              AND store_id = :store_id
            ORDER BY period_start DESC, period_end DESC, id DESC
            """
        ),
        {
            "campaign_id": campaign["id"],
            "store_id": tenant.store_id,
        },
    ).mappings().all()

    return [
        {
            "period_start": row["period_start"].isoformat(),
            "period_end": row["period_end"].isoformat(),
            "impressions": row["impressions"],
            "clicks": row["clicks"],
            "spend_minor": row["spend_minor"],
            "ctr": (
                float(row["ctr"]) if row["ctr"] is not None else None
            ),
            "cpc_minor": row["cpc_minor"],
            "conversions": row["platform_conversions"],
        }
        for row in rows
    ]


__all__ = [
    "SignalValidationError",
    "list_signals",
    "write_signals",
]
