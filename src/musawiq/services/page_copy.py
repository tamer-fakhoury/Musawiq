"""Landing page copy generation, claim filtering, and merchant edits."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping
from typing import Annotated, Any

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.ai.providers import ProviderError, get_provider
from musawiq.db.tenant import TenantContext

PROMPT_VERSION_PAGE_COPY = "page-copy-v1"

SYSTEM_PROMPT = """You write landing page copy for an e-commerce product.
Reply in the requested language and return strict JSON.

Rules:
- Return JSON only. Do not use markdown fences or prose outside the JSON object.
- Follow the supplied JSON schema exactly and do not add extra fields.
- Never make medical, absolute, or guaranteed claims and never promise results.
- Do not invent prices, discounts, certifications, or product facts that are \
not in the supplied context.
"""

_CLAIM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "medical",
        re.compile(
            r"(علاج|يعالج|معالج|شفاء|دواء|طبي|طبية|"
            r"\bcure\b|\btreat(s|ment)?\b|\btherapy\b|\bheal(s|ing)?\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "guaranteed",
        re.compile(
            r"(مضمون|نضمن|ضمان النتائج|نتائج مؤكدة|نتيجة مؤكدة|"
            r"\bguarantee(d|s)?\b|\bguaranteed results?\b|\bpromise(d|s)?\b|"
            r"\brisk[- ]free\b|\b100%\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "absolute",
        re.compile(
            r"(الأفضل|أفضل من|رقم واحد|رقم 1|الأقوى|مطلق|دائما|أبدا|"
            r"\bbest\b|\bnumber one\b|#1|\balways\b|\bnever\b|\bultimate\b|"
            r"\bperfect\b)",
            re.IGNORECASE,
        ),
    ),
)

CopyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PageCopy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: CopyText
    description: CopyText
    cta_label: CopyText
    body: CopyText


class PageCopyError(Exception):
    """Base class for landing page copy failures."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _reject_claims(*values: str) -> None:
    for value in values:
        for kind, pattern in _CLAIM_PATTERNS:
            if pattern.search(value):
                raise PageCopyError(
                    "claim_rejected",
                    f"Copy contains a rejected {kind} claim.",
                )


def _page_version(session: Session, tenant: TenantContext, page_id: object):
    try:
        page_uuid = uuid.UUID(str(page_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PageCopyError("invalid_page_id", "page_id must be a UUID.") from exc
    row = session.execute(
        text(
            """
            SELECT lp.id, lp.language, lp.currency, lp.template_id,
                   lp.status, lp.current_version_id, l.direction,
                   pv.content, pv.price_minor
            FROM landing_pages AS lp
            JOIN languages AS l ON l.code = lp.language
            LEFT JOIN page_versions AS pv ON pv.id = lp.current_version_id
            WHERE lp.id = :id AND lp.store_id = :store_id
              AND lp.deleted_at IS NULL
            """
        ),
        {"id": page_uuid, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise PageCopyError("not_found", "Landing page not found.", status_code=404)
    if row["current_version_id"] is None:
        raise PageCopyError(
            "no_draft", "Landing page has no draft content yet.", status_code=409
        )
    return row


def _write_copy(session: Session, row: Mapping[str, Any], copy: dict[str, Any]) -> None:
    content = dict(row["content"] or {})
    content["copy"] = copy
    if row["status"] != "published":
        session.execute(
            text(
                "UPDATE page_versions SET content = :content WHERE id = :id"
            ),
            {"id": row["current_version_id"], "content": Jsonb(content)},
        )
        return

    next_version = session.execute(
        text(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM page_versions "
            "WHERE landing_page_id = :id"
        ),
        {"id": row["id"]},
    ).scalar_one()
    version_id = session.execute(
        text(
            """
            INSERT INTO page_versions (
                store_id, landing_page_id, version, content, price_minor,
                currency, image_file_ids, order_channel_id, generated_by,
                model_version, created_by
            )
            SELECT store_id, landing_page_id, :version, :content, price_minor,
                   currency, image_file_ids, order_channel_id, generated_by,
                   model_version, created_by
            FROM page_versions
            WHERE id = :current_version_id
            RETURNING id
            """
        ),
        {
            "version": next_version,
            "content": Jsonb(content),
            "current_version_id": row["current_version_id"],
        },
    ).scalar_one()
    session.execute(
        text(
            """
            UPDATE landing_pages
            SET current_version_id = :version_id,
                published_version_id = :version_id,
                published_at = now()
            WHERE id = :id
            """
        ),
        {"id": row["id"], "version_id": version_id},
    )


def _existing_copy(row: Mapping[str, Any]) -> dict[str, Any] | None:
    content = row["content"] or {}
    copy = content.get("copy")
    return copy if isinstance(copy, dict) else None


def generate_copy(
    session: Session,
    tenant: TenantContext,
    page_id: object,
    *,
    force: bool = False,
    provider: Any = None,
) -> dict[str, Any]:
    row = _page_version(session, tenant, page_id)
    current = _existing_copy(row)
    if current and current.get("edited") and not force:
        raise PageCopyError(
            "manual_edits_exist",
            "Manual copy edits exist; pass force=true to regenerate.",
            status_code=409,
        )

    provider = provider or get_provider()
    if getattr(provider, "available", True) is False:
        raise PageCopyError(
            "ai_unavailable",
            str(getattr(provider, "degraded_reason", None) or "The AI provider is unavailable."),
            status_code=503,
        )

    content = row["content"] or {}
    context = {
        "language": row["language"],
        "direction": row["direction"],
        "product": {
            "name": content.get("name"),
            "description": content.get("description"),
            "price_minor": row["price_minor"],
            "currency": row["currency"].strip(),
            "target_market": content.get("target_market"),
        },
    }
    user_prompt = (
        f"Write landing page copy in language {row['language']!r}.\n"
        "Context JSON:\n"
        + json.dumps(context, ensure_ascii=False, sort_keys=True)
    )
    try:
        payload = provider.generate_json(
            SYSTEM_PROMPT, user_prompt, PageCopy.model_json_schema()
        )
        result = PageCopy.model_validate(payload)
    except (ProviderError, ValidationError) as exc:
        raise PageCopyError(
            "ai_invalid_output",
            "The AI provider returned invalid copy JSON.",
            status_code=502,
        ) from exc

    _reject_claims(
        result.headline, result.description, result.cta_label, result.body
    )
    copy = {
        "headline": result.headline,
        "description": result.description,
        "cta_label": result.cta_label,
        "body": result.body,
        "language": row["language"],
        "direction": row["direction"],
        "generated_by": "ai",
        "model_version": getattr(provider, "model_version", PROMPT_VERSION_PAGE_COPY),
        "edited": False,
    }
    _write_copy(session, row, copy)
    return copy


def update_copy(
    session: Session,
    tenant: TenantContext,
    page_id: object,
    *,
    fields: Mapping[str, Any],
) -> dict[str, Any]:
    row = _page_version(session, tenant, page_id)
    existing = _existing_copy(row)
    if existing is None:
        raise PageCopyError(
            "copy_missing", "Generate copy before editing it.", status_code=409
        )

    allowed = ("headline", "description", "cta_label", "body")
    merged = {key: existing.get(key, "") for key in allowed}
    for key, value in fields.items():
        if key not in allowed:
            raise PageCopyError("invalid_field", f"Unknown copy field {key!r}.")
        if not isinstance(value, str) or not value.strip():
            raise PageCopyError(
                "invalid_copy", f"{key} must be a non-empty string."
            )
        merged[key] = value.strip()

    _reject_claims(*(merged[key] for key in allowed))
    copy = {
        **existing,
        **merged,
        "edited": True,
    }
    _write_copy(session, row, copy)
    return copy


__all__ = [
    "PROMPT_VERSION_PAGE_COPY",
    "PageCopy",
    "PageCopyError",
    "SYSTEM_PROMPT",
    "generate_copy",
    "update_copy",
]
