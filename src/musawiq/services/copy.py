"""AI copy suggestions for manual merchant edits (never persisted)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    ValidationError,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.ai.providers import get_provider
from musawiq.ai.providers.base import ProviderError
from musawiq.db.tenant import TenantContext

PROMPT_VERSION_COPY = "copy-v1"

SYSTEM_PROMPT = """You write advertising copy for an Arabic-speaking merchant. \
Reply in Modern Standard Arabic and return strict JSON.

Rules:
- Write every Arabic field in Modern Standard Arabic.
- Return JSON only. Do not use markdown fences or prose outside the JSON object.
- Follow the supplied JSON schema exactly and do not add extra fields.
- Never make medical, absolute, or guaranteed claims and never promise results.
- Do not invent prices, discounts, certifications, or product facts that are \
not in the supplied context.
- Produce exactly the requested number of distinct variants.
"""

CopyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class CopyVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: CopyText
    copy_text: CopyText
    description: CopyText
    angle_ar: CopyText


class CopySuggestions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variants: list[CopyVariant]


class CopyError(Exception):
    """Base class for copy suggestion failures."""


class CopyNotFound(CopyError):
    """Raised when the campaign or ad set is outside the tenant."""


class CopyValidationError(CopyError):
    """Raised when the request is invalid."""


class CopyUnavailable(CopyError):
    """Raised when the configured provider cannot generate content."""


class CopyProviderError(CopyError):
    """Raised when the provider returns unusable output."""


def _campaign(
    session: Session,
    tenant: TenantContext,
    campaign_id: uuid.UUID | str,
) -> Mapping[str, Any]:
    try:
        campaign_uuid = uuid.UUID(str(campaign_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise CopyValidationError("campaign_id must be a valid UUID") from exc

    row = session.execute(
        text(
            """
            SELECT c.provider, c.objective, c.budget_type, c.budget_minor,
                   c.currency, pc.name AS concept_name,
                   pc.description AS concept_description,
                   pc.price_minor AS concept_price_minor
            FROM campaigns c
            LEFT JOIN tests t
              ON t.id = c.test_id AND t.store_id = c.store_id
            LEFT JOIN product_concepts pc
              ON pc.id = t.product_concept_id AND pc.store_id = c.store_id
            WHERE c.id = :campaign_id AND c.store_id = :store_id
            """
        ),
        {"campaign_id": campaign_uuid, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise CopyNotFound("Campaign not found")
    return row


def _audience(
    session: Session, tenant: TenantContext
) -> dict[str, Any] | None:
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
            SELECT locations, age_min, age_max FROM audience_segments
            WHERE store_id = :store_id AND audience_profile_id = :profile_id
            """
        ),
        {"store_id": tenant.store_id, "profile_id": profile["id"]},
    ).mappings().all()

    locations: set[str] = set()
    age_min: int | None = None
    age_max: int | None = None
    for segment in segments:
        if isinstance(segment["locations"], list):
            locations.update(
                item
                for item in segment["locations"]
                if isinstance(item, str)
            )
        if age_min is None or segment["age_min"] < age_min:
            age_min = segment["age_min"]
        if age_max is None or segment["age_max"] > age_max:
            age_max = segment["age_max"]

    return {
        "languages": list(profile["languages"] or []),
        "segment_count": len(segments),
        "locations": sorted(locations),
        "age_min": age_min,
        "age_max": age_max,
    }


def _targeting(
    session: Session,
    tenant: TenantContext,
    campaign_id: uuid.UUID,
    adset_id: uuid.UUID | None,
) -> list[dict[str, Any]]:
    if adset_id is not None:
        row = session.execute(
            text(
                """
                SELECT targeting FROM ad_sets
                WHERE id = :adset_id AND campaign_id = :campaign_id
                  AND store_id = :store_id
                """
            ),
            {
                "adset_id": adset_id,
                "campaign_id": campaign_id,
                "store_id": tenant.store_id,
            },
        ).mappings().one_or_none()
        if row is None:
            raise CopyNotFound("Ad set not found")
        return [row["targeting"]]

    rows = session.execute(
        text(
            """
            SELECT targeting FROM ad_sets
            WHERE campaign_id = :campaign_id AND store_id = :store_id
            ORDER BY created_at, id
            """
        ),
        {"campaign_id": campaign_id, "store_id": tenant.store_id},
    ).mappings().all()
    return [row["targeting"] for row in rows]


def _existing_variations(
    session: Session, tenant: TenantContext, campaign_id: uuid.UUID
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT v.headline, v.copy_text FROM ad_variations v
            JOIN ad_sets s ON s.id = v.adset_id
            WHERE s.campaign_id = :campaign_id
              AND s.store_id = :store_id
              AND v.store_id = :store_id
            ORDER BY v.created_at, v.id
            """
        ),
        {"campaign_id": campaign_id, "store_id": tenant.store_id},
    ).mappings().all()
    return [
        {"headline": row["headline"], "copy_text": row["copy_text"]}
        for row in rows
    ]


def _provider_reason(provider: Any) -> str:
    reason = getattr(provider, "degraded_reason", None)
    return str(reason or "The AI provider is unavailable.")


def suggest_copy(
    session: Session,
    tenant: TenantContext,
    campaign_id: uuid.UUID | str,
    *,
    adset_id: uuid.UUID | str | None = None,
    count: int = 3,
    notes: str | None = None,
    provider: Any = None,
) -> dict[str, Any]:
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or not 1 <= count <= 5
    ):
        raise CopyValidationError("count must be between 1 and 5")
    if notes is not None and not isinstance(notes, str):
        raise CopyValidationError("notes must be a string")

    campaign = _campaign(session, tenant, campaign_id)
    campaign_uuid = uuid.UUID(str(campaign_id))

    adset_uuid: uuid.UUID | None = None
    if adset_id is not None:
        try:
            adset_uuid = uuid.UUID(str(adset_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise CopyValidationError("adset_id must be a valid UUID") from exc

    concept = None
    if campaign["concept_name"] is not None:
        concept = {
            "name": campaign["concept_name"],
            "description": campaign["concept_description"],
            "price_minor": campaign["concept_price_minor"],
            "currency": campaign["currency"].strip(),
        }

    context = {
        "concept": concept,
        "audience": _audience(session, tenant),
        "campaign": {
            "provider": campaign["provider"],
            "objective": campaign["objective"],
            "budget_type": campaign["budget_type"],
            "budget_minor": campaign["budget_minor"],
            "currency": campaign["currency"].strip(),
            "targeting": _targeting(
                session, tenant, campaign_uuid, adset_uuid
            ),
        },
        "existing_variations": _existing_variations(
            session, tenant, campaign_uuid
        ),
    }

    provider = provider or get_provider()
    if getattr(provider, "available", True) is False:
        raise CopyUnavailable(_provider_reason(provider))

    user_prompt = (
        f"Write exactly {count} advertising copy variants.\n"
        f"Merchant notes: {notes.strip() if notes else 'none'}\n"
        "Context JSON:\n"
        + json.dumps(context, ensure_ascii=False, sort_keys=True)
    )

    try:
        payload = provider.generate_json(
            SYSTEM_PROMPT,
            user_prompt,
            CopySuggestions.model_json_schema(),
        )
    except ProviderError as exc:
        raise CopyProviderError(
            "The AI provider returned invalid copy JSON."
        ) from exc

    try:
        result = CopySuggestions.model_validate(payload)
    except ValidationError as exc:
        raise CopyProviderError(
            "The AI provider returned invalid copy JSON."
        ) from exc

    if len(result.variants) != count:
        raise CopyProviderError(
            "The AI provider did not return the requested number of variants."
        )

    return {
        "variants": [variant.model_dump() for variant in result.variants]
    }


__all__ = [
    "CopyError",
    "CopyNotFound",
    "CopyProviderError",
    "CopySuggestions",
    "CopyUnavailable",
    "CopyValidationError",
    "CopyVariant",
    "PROMPT_VERSION_COPY",
    "SYSTEM_PROMPT",
    "suggest_copy",
]
