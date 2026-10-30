"""Campaign ad copy variation generation (FR-3.2.1)."""

from __future__ import annotations

import difflib
import json
import re
import uuid
from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.ai.providers import ProviderError, get_provider
from musawiq.db.tenant import TenantContext
from musawiq.services.landing_pages import PUBLIC_BASE_URL
from musawiq.services.page_copy import PageCopyError, reject_claims

PROMPT_VERSION_AD_VARIATIONS = "ad-variations-v1"
DEFAULT_COUNT = 3
MAX_COUNT = 5
DUPLICATE_THRESHOLD = 0.85

PLATFORM_LIMITS: dict[str, dict[str, int]] = {
    "meta": {"name": 100, "headline": 40, "description": 125, "copy_text": 125},
    "google": {"name": 100, "headline": 30, "description": 90, "copy_text": 90},
    "tiktok": {"name": 100, "headline": 40, "description": 100, "copy_text": 100},
    "snapchat": {"name": 100, "headline": 34, "description": 110, "copy_text": 110},
}

SYSTEM_PROMPT = """You write ad copy variants for an e-commerce campaign.
Reply in the requested language and return strict JSON.

Rules:
- Return JSON only. Do not use markdown fences or prose outside the JSON object.
- Follow the supplied JSON schema exactly and do not add extra fields.
- Respect the per-field character limits supplied in the request.
- Never make medical, absolute, or guaranteed claims and never promise results.
- Do not invent prices, discounts, certifications, or product facts that are \
not in the supplied context.
- Every variation must use a distinct angle.
"""

CopyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class VariationCopy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CopyText
    headline: CopyText
    copy_text: CopyText
    description: CopyText


class VariationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variations: list[VariationCopy]


class AdVariationError(Exception):
    """Base class for ad variation generation failures."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _limits(provider: str) -> dict[str, int]:
    return PLATFORM_LIMITS.get(provider.strip().lower(), PLATFORM_LIMITS["meta"])


def _truncate(value: str, limit: int) -> str:
    clean = value.strip()
    return clean if len(clean) <= limit else clean[:limit].rstrip()


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", value.lower()).strip()


def _is_near_duplicate(first: str, second: str) -> bool:
    left, right = _normalized(first), _normalized(second)
    if not left or not right:
        return False
    return difflib.SequenceMatcher(None, left, right).ratio() >= DUPLICATE_THRESHOLD


def _context(
    session: Session, tenant: TenantContext, campaign_id: uuid.UUID, adset_id: uuid.UUID
) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            SELECT c.provider, c.currency, c.test_id,
                   pc.name AS product_name, pc.description AS product_description,
                   pc.price_minor, pc.currency AS product_currency,
                   lp.id AS landing_page_id, lp.slug, lp.language,
                   lp.published_url, pv.content AS page_content,
                   s.default_language
            FROM campaigns AS c
            JOIN tests AS t ON t.id = c.test_id
            JOIN product_concepts AS pc ON pc.id = t.product_concept_id
            LEFT JOIN landing_pages AS lp
                ON lp.test_id = t.id AND lp.deleted_at IS NULL
            LEFT JOIN page_versions AS pv ON pv.id = lp.current_version_id
            JOIN stores AS s ON s.id = c.store_id
            WHERE c.id = :campaign_id AND c.store_id = :store_id
            ORDER BY lp.updated_at DESC NULLS LAST
            LIMIT 1
            """
        ),
        {"campaign_id": campaign_id, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise AdVariationError(
            "not_found", "Campaign not found.", status_code=404
        )
    adset = session.execute(
        text(
            "SELECT 1 FROM ad_sets "
            "WHERE id = :id AND campaign_id = :campaign_id AND store_id = :store_id"
        ),
        {"id": adset_id, "campaign_id": campaign_id, "store_id": tenant.store_id},
    ).scalar_one_or_none()
    if adset is None:
        raise AdVariationError(
            "not_found", "Ad set not found.", status_code=404
        )
    if row["test_id"] is None:
        raise AdVariationError(
            "campaign_without_product",
            "Campaign must be linked to a product test.",
        )

    destination = row["published_url"]
    if not destination and row["slug"]:
        destination = f"{PUBLIC_BASE_URL}/p/{row['slug']}"
    if not destination:
        raise AdVariationError(
            "landing_page_required",
            "Campaign needs a landing page to link ad variations.",
        )
    content = row["page_content"] or {}
    copy = content.get("copy") if isinstance(content, dict) else None
    return {
        "campaign_id": str(campaign_id),
        "provider": row["provider"],
        "language": row["language"] or row["default_language"],
        "destination_url": destination,
        "product": {
            "name": row["product_name"],
            "description": row["product_description"],
            "price_minor": row["price_minor"],
            "currency": (row["product_currency"] or row["currency"]).strip(),
        },
        "page_copy": copy if isinstance(copy, dict) else None,
    }


def _existing_texts(
    session: Session, tenant: TenantContext, adset_id: uuid.UUID
) -> list[str]:
    rows = session.execute(
        text(
            "SELECT copy_text FROM ad_variations "
            "WHERE adset_id = :adset_id AND store_id = :store_id"
        ),
        {"adset_id": adset_id, "store_id": tenant.store_id},
    ).scalars().all()
    return [row for row in rows if row]


def generate_variations(
    session: Session,
    tenant: TenantContext,
    campaign_id: uuid.UUID | str,
    payload: Mapping[str, Any],
    *,
    provider: Any = None,
) -> dict[str, Any]:
    try:
        campaign_uuid = uuid.UUID(str(campaign_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AdVariationError(
            "invalid_campaign_id", "campaign_id must be a UUID."
        ) from exc

    count = payload.get("count", DEFAULT_COUNT)
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= MAX_COUNT:
        raise AdVariationError(
            "invalid_count", f"count must be between 1 and {MAX_COUNT}."
        )
    notes = payload.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise AdVariationError("invalid_notes", "notes must be a string.")
    raw_adset_id = payload.get("adset_id")
    if raw_adset_id is None:
        raise AdVariationError("invalid_adset", "adset_id is required.")
    try:
        adset_uuid = uuid.UUID(str(raw_adset_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AdVariationError("invalid_adset", "adset_id must be a UUID.") from exc

    context = _context(session, tenant, campaign_uuid, adset_uuid)
    limits = _limits(context["provider"])

    provider = provider or get_provider()
    if getattr(provider, "available", True) is False:
        raise AdVariationError(
            "ai_unavailable",
            str(
                getattr(provider, "degraded_reason", None)
                or "The AI provider is unavailable."
            ),
            status_code=503,
        )

    request = {
        "language": context["language"],
        "provider": context["provider"],
        "character_limits": limits,
        "product": context["product"],
        "landing_page_copy": context["page_copy"],
        "variation_count": count,
        "merchant_notes": (notes or "").strip() or None,
    }
    user_prompt = (
        f"Write exactly {count} ad variations.\n"
        "Context JSON:\n"
        + json.dumps(request, ensure_ascii=False, sort_keys=True)
    )
    try:
        raw = provider.generate_json(
            SYSTEM_PROMPT, user_prompt, VariationBatch.model_json_schema()
        )
        batch = VariationBatch.model_validate(raw)
    except (ProviderError, ValidationError) as exc:
        raise AdVariationError(
            "ai_invalid_output",
            "The AI provider returned invalid ad variation JSON.",
            status_code=502,
        ) from exc
    if len(batch.variations) != count:
        raise AdVariationError(
            "ai_invalid_output",
            "The AI provider did not return the requested number of variations.",
            status_code=502,
        )

    try:
        for variation in batch.variations:
            reject_claims(
                variation.name,
                variation.headline,
                variation.copy_text,
                variation.description,
            )
    except PageCopyError as exc:
        raise AdVariationError(exc.code, exc.message, exc.status_code) from exc

    existing = _existing_texts(session, tenant, adset_uuid)
    seen: list[tuple[str, str]] = [("existing", text_value) for text_value in existing]
    results: list[dict[str, Any]] = []
    for variation in batch.variations:
        body = _truncate(variation.copy_text, limits["copy_text"])
        duplicate_of = None
        for label, seen_text in seen:
            if _is_near_duplicate(body, seen_text):
                duplicate_of = label
                break
        row = session.execute(
            text(
                """
                INSERT INTO ad_variations (
                    store_id, adset_id, name, copy_text, headline,
                    description, destination_url, status
                ) VALUES (
                    :store_id, :adset_id, :name, :copy_text, :headline,
                    :description, :destination_url, 'draft'
                )
                RETURNING id, adset_id, name, copy_text, headline,
                          description, destination_url, status,
                          created_at, updated_at
                """
            ),
            {
                "store_id": tenant.store_id,
                "adset_id": adset_uuid,
                "name": _truncate(variation.name, limits["name"]),
                "copy_text": body,
                "headline": _truncate(variation.headline, limits["headline"]),
                "description": _truncate(
                    variation.description, limits["description"]
                ),
                "destination_url": context["destination_url"],
            },
        ).mappings().one()
        normalized_seen_append = (str(row["id"]), body)
        seen.append(normalized_seen_append)
        results.append(
            {
                "id": str(row["id"]),
                "adset_id": str(row["adset_id"]),
                "name": row["name"],
                "headline": row["headline"],
                "copy_text": row["copy_text"],
                "description": row["description"],
                "destination_url": row["destination_url"],
                "status": row["status"],
                "near_duplicate": duplicate_of is not None,
                "duplicate_of": duplicate_of,
            }
        )
    return {
        "provider": context["provider"],
        "language": context["language"],
        "limits": limits,
        "variations": results,
    }


__all__ = [
    "AdVariationError",
    "DEFAULT_COUNT",
    "DUPLICATE_THRESHOLD",
    "MAX_COUNT",
    "PLATFORM_LIMITS",
    "PROMPT_VERSION_AD_VARIATIONS",
    "SYSTEM_PROMPT",
    "generate_variations",
]
