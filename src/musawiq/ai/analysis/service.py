"""Validate AI analysis output against the fixed schema and supplied signals."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from psycopg.types.json import Jsonb
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.ai.analysis.prompt import PROMPT_VERSION, SYSTEM_PROMPT
from musawiq.ai.analysis.schema import AnalysisResult
from musawiq.ai.providers import get_provider
from musawiq.ai.providers.base import ProviderError
from musawiq.db.tenant import TenantContext
from musawiq.services.campaigns import config_fingerprint

TOLERANCE = 0.01
RATE_LIMIT = 10


class AnalysisValidationError(ValueError):
    """Raised when analysis output is malformed or unsupported by evidence."""


class AnalysisNotFound(LookupError):
    """Raised when the campaign or analysis is outside the tenant."""


class AnalysisRateLimited(RuntimeError):
    """Raised when a store exceeds the hourly analysis budget."""


def _matches(observed: float, supplied: object) -> bool:
    try:
        expected = float(supplied)
    except (TypeError, ValueError) as exc:
        raise AnalysisValidationError(
            "supplied metric is not numeric"
        ) from exc
    if expected == 0:
        return observed == 0
    return abs(observed - expected) / abs(expected) <= TOLERANCE


def validate_result(
    payload: dict,
    supplied_metrics: dict,
) -> AnalysisResult:
    try:
        result = AnalysisResult.model_validate(payload)
    except ValidationError as exc:
        raise AnalysisValidationError(
            "analysis result does not match the required schema"
        ) from exc

    for issue in result.issues:
        if issue.metric not in supplied_metrics:
            raise AnalysisValidationError(
                f"issue cites unknown metric: {issue.metric}"
            )
        if not _matches(issue.observed, supplied_metrics[issue.metric]):
            raise AnalysisValidationError(
                f"issue observed value does not match supplied metric: "
                f"{issue.metric}"
            )
    return result


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _campaign(
    session: Session,
    tenant: TenantContext,
    campaign_id: uuid.UUID | str,
) -> Mapping[str, Any]:
    row = session.execute(
        text(
            """
            SELECT c.provider, c.objective, c.budget_type, c.budget_minor,
                   c.currency, pc.name AS concept_name,
                   pc.description AS concept_description,
                   pc.price_minor AS concept_price_minor,
                   pc.cost_minor AS concept_cost_minor
            FROM campaigns c
            LEFT JOIN tests t
              ON t.id = c.test_id AND t.store_id = c.store_id
            LEFT JOIN product_concepts pc
              ON pc.id = t.product_concept_id AND pc.store_id = c.store_id
            WHERE c.id = :campaign_id AND c.store_id = :store_id
            """
        ),
        {"campaign_id": campaign_id, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise AnalysisNotFound("Campaign not found")
    return row


def _rate_limit(session: Session, tenant: TenantContext) -> None:
    count = session.execute(
        text(
            """
            SELECT count(*) FROM ai_analyses
            WHERE store_id = :store_id
              AND created_at >= now() - interval '1 hour'
            """
        ),
        {"store_id": tenant.store_id},
    ).scalar_one()
    if int(count) >= RATE_LIMIT:
        raise AnalysisRateLimited(
            "The hourly analysis limit has been reached."
        )


def _metrics(values: Mapping[str, Any]) -> dict[str, Any]:
    impressions = int(values.get("impressions") or 0)
    clicks = int(values.get("clicks") or 0)
    spend_minor = int(values.get("spend_minor") or 0)
    conversions = int(values.get("conversions") or 0)
    return {
        "impressions": impressions,
        "reach": int(values.get("reach") or 0),
        "clicks": clicks,
        "spend_minor": spend_minor,
        "conversions": conversions,
        "ctr": (clicks / impressions) if impressions else None,
        "cpc_minor": (spend_minor / clicks) if clicks else None,
        "cpm_minor": (
            spend_minor * 1000 / impressions if impressions else None
        ),
        "cost_per_conversion_minor": (
            spend_minor / conversions if conversions else None
        ),
    }


def _signals(session: Session, tenant: TenantContext, campaign_id: Any, start: datetime, end: datetime) -> dict[str, Any]:
    rows = session.execute(
        text(
            """
            SELECT ad_variation_id,
                   COALESCE(SUM(impressions), 0) AS impressions,
                   COALESCE(SUM(reach), 0) AS reach,
                   COALESCE(SUM(clicks), 0) AS clicks,
                   COALESCE(SUM(spend_minor), 0) AS spend_minor,
                   COALESCE(SUM(platform_conversions), 0) AS conversions
            FROM metric_snapshots
            WHERE store_id = :store_id
              AND campaign_id = :campaign_id
              AND period_start >= :window_start
              AND period_end <= :window_end
            GROUP BY ad_variation_id
            ORDER BY ad_variation_id NULLS LAST
            """
        ),
        {
            "store_id": tenant.store_id,
            "campaign_id": campaign_id,
            "window_start": start,
            "window_end": end,
        },
    ).mappings().all()

    ads = []
    totals = {
        "impressions": 0,
        "reach": 0,
        "clicks": 0,
        "spend_minor": 0,
        "conversions": 0,
    }
    for row in rows:
        values = _metrics(row)
        ads.append(
            {
                "ad_variation_id": (
                    str(row["ad_variation_id"])
                    if row["ad_variation_id"]
                    else None
                ),
                **values,
            }
        )
        for key in totals:
            totals[key] += values[key]
    return {"totals": _metrics(totals), "ads": ads}


def _audience(session: Session, tenant: TenantContext) -> dict[str, Any] | None:
    profile = session.execute(
        text(
            """
            SELECT id, languages FROM audience_profiles
            WHERE store_id = :store_id AND is_current
            ORDER BY version DESC
            LIMIT 1
            """
        ),
        {"store_id": tenant.store_id},
    ).mappings().one_or_none()
    if profile is None:
        return None

    segments = session.execute(
        text(
            """
            SELECT locations FROM audience_segments
            WHERE store_id = :store_id AND audience_profile_id = :profile_id
            """
        ),
        {"store_id": tenant.store_id, "profile_id": profile["id"]},
    ).mappings().all()

    locales: set[str] = set()
    for row in segments:
        locations = row["locations"]
        if isinstance(locations, list):
            locales.update(item for item in locations if isinstance(item, str))

    return {
        "languages": list(profile["languages"] or []),
        "segment_count": len(segments),
        "locales": sorted(locales),
    }


def _snapshot(
    session: Session,
    tenant: TenantContext,
    campaign_id: uuid.UUID | str,
    campaign: Mapping[str, Any],
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    adsets = session.execute(
        text(
            """
            SELECT targeting FROM ad_sets
            WHERE store_id = :store_id AND campaign_id = :campaign_id
            ORDER BY created_at, id
            """
        ),
        {"store_id": tenant.store_id, "campaign_id": campaign_id},
    ).mappings().all()

    variations = session.execute(
        text(
            """
            SELECT v.id, v.headline, v.copy_text, v.status
            FROM ad_variations v
            JOIN ad_sets s ON s.id = v.adset_id
            WHERE s.store_id = :store_id
              AND v.store_id = :store_id
              AND s.campaign_id = :campaign_id
            ORDER BY v.created_at, v.id
            """
        ),
        {"store_id": tenant.store_id, "campaign_id": campaign_id},
    ).mappings().all()

    concept = None
    if campaign["concept_name"] is not None:
        concept = {
            "name": campaign["concept_name"],
            "description": campaign["concept_description"],
            "price_minor": campaign["concept_price_minor"],
            "cost_minor": campaign["concept_cost_minor"],
        }

    return {
        "schema_version": 1,
        "window": {"start": _iso(start), "end": _iso(end)},
        "campaign": {
            "provider": campaign["provider"],
            "objective": campaign["objective"],
            "budget_type": campaign["budget_type"],
            "budget_minor": campaign["budget_minor"],
            "currency": campaign["currency"].strip(),
            "targeting": [row["targeting"] for row in adsets],
        },
        "signals": _signals(session, tenant, campaign_id, start, end),
        "concept": concept,
        "audience": _audience(session, tenant),
        "ad_variations": [
            {
                "id": str(row["id"]),
                "headline": row["headline"],
                "copy_text": row["copy_text"],
                "status": row["status"],
            }
            for row in variations
        ],
        "config_fingerprint": config_fingerprint(
            session, tenant, campaign_id
        ),
    }


def _analysis_out(row: Mapping[str, Any]) -> dict[str, Any]:
    confidence = row["confidence"]
    return {
        "id": str(row["id"]),
        "campaign_id": str(row["campaign_id"]),
        "parent_analysis_id": (
            str(row["parent_analysis_id"])
            if row["parent_analysis_id"]
            else None
        ),
        "window_start": _iso(row["window_start"]),
        "window_end": _iso(row["window_end"]),
        "status": row["status"],
        "provider": row["provider"],
        "model_version": row["model_version"],
        "prompt_version": row["prompt_version"],
        "input_snapshot": row["input_snapshot"],
        "result": row["result"],
        "demand_level": row["demand_level"],
        "confidence": float(confidence) if confidence is not None else None,
        "created_at": _iso(row["created_at"]),
    }


def _persist(
    session: Session,
    tenant: TenantContext,
    campaign_id: uuid.UUID | str,
    *,
    start: datetime,
    end: datetime,
    status: str,
    provider: Any,
    snapshot: dict[str, Any],
    result: dict[str, Any] | None,
    demand_level: str | None = None,
    confidence: float | None = None,
) -> Mapping[str, Any]:
    return session.execute(
        text(
            """
            INSERT INTO ai_analyses (
                store_id, campaign_id, window_start, window_end, status,
                provider, model_version, prompt_version, input_snapshot,
                result, demand_level, confidence, created_by
            ) VALUES (
                :store_id, :campaign_id, :window_start, :window_end, :status,
                :provider, :model_version, :prompt_version, :input_snapshot,
                :result, :demand_level, :confidence, :created_by
            )
            RETURNING *
            """
        ),
        {
            "store_id": tenant.store_id,
            "campaign_id": campaign_id,
            "window_start": start,
            "window_end": end,
            "status": status,
            "provider": getattr(provider, "provider", "unknown"),
            "model_version": getattr(provider, "model_version", ""),
            "prompt_version": PROMPT_VERSION,
            "input_snapshot": Jsonb(snapshot),
            "result": Jsonb(result) if result is not None else None,
            "demand_level": demand_level,
            "confidence": confidence,
            "created_by": tenant.user_id,
        },
    ).mappings().one()


def _degraded_reason(provider: Any) -> str:
    reason = getattr(provider, "degraded_reason", None)
    if reason:
        return str(reason)
    generator = getattr(provider, "generate", None)
    if callable(generator):
        try:
            result = generator(
                "",
                model_version="",
                prompt_version=PROMPT_VERSION,
                input_snapshot_ref={},
            )
            reason = getattr(result, "degraded_reason", None)
        except Exception:
            reason = None
    return str(reason or "The AI provider is unavailable.")


def create_analysis(
    session: Session,
    tenant: TenantContext,
    campaign_id: uuid.UUID | str,
    *,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    provider: Any = None,
) -> dict[str, Any]:
    campaign = _campaign(session, tenant, campaign_id)
    _rate_limit(session, tenant)

    end = _utc(window_end) or datetime.now(timezone.utc)
    start = _utc(window_start) or end - timedelta(days=7)
    if start >= end:
        raise AnalysisValidationError(
            "window_start must be before window_end"
        )

    provider = provider or get_provider()
    snapshot = _snapshot(
        session, tenant, campaign_id, campaign, start, end
    )
    supplied_metrics = snapshot["signals"]["totals"]

    if getattr(provider, "available", True) is False:
        reason = _degraded_reason(provider)
        row = _persist(
            session,
            tenant,
            campaign_id,
            start=start,
            end=end,
            status="degraded",
            provider=provider,
            snapshot=snapshot,
            result={"degraded_reason": reason},
        )
        return _analysis_out(row)

    user_prompt = (
        "Analyse this campaign data and return the JSON object now:\n"
        + json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    )
    try:
        payload = provider.generate_json(
            SYSTEM_PROMPT,
            user_prompt,
            AnalysisResult.model_json_schema(),
        )
    except ProviderError as exc:
        reason = str(exc) or "The AI provider returned invalid output."
        _persist(
            session,
            tenant,
            campaign_id,
            start=start,
            end=end,
            status="failed",
            provider=provider,
            snapshot=snapshot,
            result={"error": reason},
        )
        raise AnalysisValidationError(reason) from exc

    try:
        result = validate_result(payload, supplied_metrics)
    except AnalysisValidationError as exc:
        _persist(
            session,
            tenant,
            campaign_id,
            start=start,
            end=end,
            status="failed",
            provider=provider,
            snapshot=snapshot,
            result={"error": str(exc)},
        )
        raise

    row = _persist(
        session,
        tenant,
        campaign_id,
        start=start,
        end=end,
        status="succeeded",
        provider=provider,
        snapshot=snapshot,
        result=result.model_dump(mode="json"),
        demand_level=result.demand.level,
        confidence=result.demand.confidence,
    )
    return _analysis_out(row)


def list_analyses(
    session: Session,
    tenant: TenantContext,
    campaign_id: uuid.UUID | str,
) -> list[dict[str, Any]]:
    _campaign(session, tenant, campaign_id)
    rows = session.execute(
        text(
            """
            SELECT id, status, demand_level, confidence, created_at
            FROM ai_analyses
            WHERE store_id = :store_id AND campaign_id = :campaign_id
            ORDER BY created_at DESC, id DESC
            """
        ),
        {"store_id": tenant.store_id, "campaign_id": campaign_id},
    ).mappings().all()
    return [
        {
            "id": str(row["id"]),
            "status": row["status"],
            "demand_level": row["demand_level"],
            "confidence": (
                float(row["confidence"])
                if row["confidence"] is not None
                else None
            ),
            "created_at": _iso(row["created_at"]),
        }
        for row in rows
    ]


def get_analysis(
    session: Session,
    tenant: TenantContext,
    analysis_id: uuid.UUID | str,
) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            SELECT * FROM ai_analyses
            WHERE id = :analysis_id AND store_id = :store_id
            """
        ),
        {"analysis_id": analysis_id, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise AnalysisNotFound("Analysis not found")
    return _analysis_out(row)


__all__ = [
    "AnalysisNotFound",
    "AnalysisRateLimited",
    "AnalysisValidationError",
    "RATE_LIMIT",
    "TOLERANCE",
    "create_analysis",
    "get_analysis",
    "list_analyses",
    "validate_result",
]
