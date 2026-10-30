"""On-demand product idea generation with provenance and deduplication.

Prototype deviation: this generator is deterministic and rules-based rather
than AI-backed. It uses the current niche and audience profile, plus historical
product sales when available. No external trend or competitive source is
configured yet, so that input is recorded as missing in the snapshot instead of
being invented. ``MODEL_VERSION`` identifies this rules model honestly.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from collections.abc import Mapping
from difflib import SequenceMatcher
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.config import get_settings
from musawiq.db.tenant import TenantContext
from musawiq.repositories.generation_runs import GenerationRunRepository
from musawiq.repositories.idea_evidences import IdeaEvidenceRepository
from musawiq.repositories.product_ideas import ProductIdeaRepository
from musawiq.services.audit import AuditService

MODEL_VERSION = "rules_v1"
MAX_REQUESTED_IDEAS = 10
IDEA_STATES = frozenset({"new", "saved", "dismissed", "converted"})
SIMILARITY_THRESHOLD = 0.85

logger = logging.getLogger("musawiq.recommendations")


class RecommendationError(Exception):
    """Base class for recommendation contract failures."""


class RecommendationNotFound(RecommendationError):
    """Raised when a run or idea is outside the active store."""


class RecommendationValidationError(RecommendationError):
    """Raised when a request or filter is invalid."""


class RecommendationGenerationError(RecommendationError):
    """Raised when generation cannot produce trustworthy ideas."""


def _iso(value: object) -> str | None:
    return value.isoformat() if value is not None else None


def _run_out(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "store_id": str(row["store_id"]),
        "requested_by": str(row["requested_by"]),
        "model_version": row["model_version"],
        "input_snapshot": row["input_snapshot"],
        "requested_count": row["requested_count"],
        "returned_count": row["returned_count"],
        "status": row["status"],
        "error_message": row["error_message"],
        "started_at": _iso(row["started_at"]),
        "finished_at": _iso(row["finished_at"]),
        "created_at": _iso(row["created_at"]),
    }


def _evidence_out(
    row: Mapping[str, Any],
    *,
    freshness_days: int,
) -> dict[str, Any]:
    published_at = row["source_published_at"]
    is_stale = (
        published_at is not None
        and (
            datetime.now(timezone.utc).date() - published_at.date()
        ).days
        > freshness_days
    )
    evidence_type = row["evidence_type"]
    source_url = (
        row["source_url"] if evidence_type == "verified" else None
    )
    return {
        "id": str(row["id"]),
        "evidence_type": evidence_type,
        "label": (
            "Verified" if evidence_type == "verified" else "AI Hypothesis"
        ),
        "claim": row["claim"],
        "source_name": row["source_name"],
        "source_url": source_url,
        "source_published_at": _iso(published_at),
        "retrieved_at": _iso(row["retrieved_at"]),
        "confidence": (
            float(row["confidence"])
            if row["confidence"] is not None
            else None
        ),
        "is_stale": is_stale,
    }


def _idea_out(
    row: Mapping[str, Any],
    evidence: list[Mapping[str, Any]],
    *,
    freshness_days: int,
) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "store_id": str(row["store_id"]),
        "generation_run_id": str(row["generation_run_id"]),
        "name": row["name"],
        "description": row["description"],
        "category_id": (
            str(row["category_id"]) if row["category_id"] is not None else None
        ),
        "niche_id": (
            str(row["niche_id"]) if row["niche_id"] is not None else None
        ),
        "rationale": row["rationale"],
        "state": row["state"],
        "dismissed_reason": row["dismissed_reason"],
        "converted_concept_id": (
            str(row["converted_concept_id"])
            if row["converted_concept_id"] is not None
            else None
        ),
        "model_version": row["model_version"],
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
        "evidence": [
            _evidence_out(item, freshness_days=freshness_days)
            for item in evidence
        ],
    }


def _normalized(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[\u0610-\u061A\u064B-\u065F\u06D6-\u06ED]", "", normalized)
    normalized = normalized.replace("\u0640", "")
    normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def _is_duplicate(
    name: str,
    description: str,
    blocked: list[str],
) -> bool:
    candidate = _normalized(f"{name} {description}")
    for existing in blocked:
        if candidate == existing:
            return True
        if SequenceMatcher(None, candidate, existing).ratio() >= (
            SIMILARITY_THRESHOLD
        ):
            return True
    return False


def _snapshot(
    session: Session,
    tenant: TenantContext,
    requested_count: int,
) -> dict[str, Any]:
    profile = session.execute(
        text(
            """
            SELECT * FROM audience_profiles
            WHERE store_id = :store_id AND is_current
            LIMIT 1
            """
        ),
        {"store_id": tenant.store_id},
    ).mappings().one_or_none()
    segments: list[dict[str, Any]] = []
    niches: list[dict[str, Any]] = []
    if profile is not None:
        segment_rows = session.execute(
            text(
                """
                SELECT label, locations, languages, interests
                FROM audience_segments
                WHERE store_id = :store_id
                  AND audience_profile_id = :profile_id
                ORDER BY created_at, id
                """
            ),
            {"store_id": tenant.store_id, "profile_id": profile["id"]},
        ).mappings().all()
        segments = [
            {
                "label": row["label"],
                "locations": list(row["locations"] or []),
                "languages": list(row["languages"] or []),
                "interests": list(row["interests"] or []),
            }
            for row in segment_rows
        ]
        if profile["niche_ids"]:
            niche_rows = session.execute(
                text(
                    """
                    SELECT id, category_id, name
                    FROM niches
                    WHERE id = ANY(CAST(:niche_ids AS uuid[]))
                    ORDER BY name, id
                    """
                ),
                {"niche_ids": list(profile["niche_ids"])},
            ).mappings().all()
            niches = [
                {
                    "id": str(row["id"]),
                    "category_id": str(row["category_id"]),
                    "name": row["name"],
                }
                for row in niche_rows
            ]

    sales_rows = session.execute(
        text(
            """
            SELECT oi.product_name_snapshot AS name,
                   p.category_id,
                   sum(oi.quantity) AS units
            FROM order_items AS oi
            JOIN orders AS o ON o.id = oi.order_id
            LEFT JOIN products AS p ON p.id = oi.product_id
            WHERE o.store_id = :store_id
              AND o.status IN ('confirmed', 'fulfilled')
            GROUP BY oi.product_name_snapshot, p.category_id
            ORDER BY units DESC, oi.product_name_snapshot
            LIMIT 20
            """
        ),
        {"store_id": tenant.store_id},
    ).mappings().all()
    sales_history = [
        {
            "product_name": row["name"],
            "category_id": (
                str(row["category_id"])
                if row["category_id"] is not None
                else None
            ),
            "units": int(row["units"]),
        }
        for row in sales_rows
    ]

    return {
        "schema_version": 1,
        "audience_profile_id": (
            str(profile["id"]) if profile is not None else None
        ),
        "audience_profile_version": (
            profile["version"] if profile is not None else None
        ),
        "niches": niches,
        "segments": segments,
        "sales_history": sales_history,
        "competitive_data": {
            "status": "missing",
            "reason": "No competitive or trend data source is configured.",
        },
        "requested_count": requested_count,
    }


def _existing_names(session: Session, tenant: TenantContext) -> list[str]:
    rows = session.execute(
        text(
            """
            SELECT name, description FROM product_concepts
            WHERE store_id = :store_id AND deleted_at IS NULL
            """
        ),
        {"store_id": tenant.store_id},
    ).mappings().all()
    return [
        _normalized(f"{row['name']} {row['description'] or ''}")
        for row in rows
    ]


def _candidate_templates(
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    niches = snapshot["niches"]
    sales = snapshot["sales_history"]
    segments = snapshot["segments"]
    interests = [
        interest
        for segment in segments
        for interest in segment["interests"]
    ]
    locations = [
        location
        for segment in segments
        for location in segment["locations"]
    ]
    niche_name = niches[0]["name"] if niches else None
    category_id = niches[0]["category_id"] if niches else None
    niche_id = niches[0]["id"] if niches else None
    top_product = sales[0]["product_name"] if sales else None
    if category_id is None and sales:
        category_id = sales[0]["category_id"]
    interest = interests[0] if interests else niche_name
    location = locations[0] if locations else "your market"

    if niche_name is None and top_product is None:
        return []
    label = niche_name or top_product or "product"
    candidates = [
        {
            "name": f"{label.title()} starter bundle",
            "description": (
                f"A curated {label} bundle for {location} customers."
            ),
            "rationale": (
                "Uses the selected niche, current audience locations, and "
                "available sales history."
            ),
        },
        {
            "name": f"Premium {label.title()} kit",
            "description": (
                f"An upgraded {label} kit positioned for repeat purchase."
            ),
            "rationale": (
                "Builds on the store's existing niche and audience profile."
            ),
        },
        {
            "name": f"{str(interest).title()} discovery set",
            "description": (
                f"A discovery set tied to the audience interest {interest}."
            ),
            "rationale": (
                "Connects the idea to stated audience interests."
            ),
        },
        {
            "name": f"{location} {label.title()} essentials",
            "description": (
                f"Everyday {label} essentials for customers in {location}."
            ),
            "rationale": (
                "Uses the audience location and the selected niche."
            ),
        },
    ]
    if top_product:
        candidates.extend(
            [
                {
                    "name": f"{top_product.title()} refill pack",
                    "description": (
                        f"A refill pack for the proven product {top_product}."
                    ),
                    "rationale": (
                        "Derived from the store's best-selling historical "
                        "product."
                    ),
                },
                {
                    "name": f"{top_product.title()} gift edition",
                    "description": (
                        f"A gift-oriented edition of {top_product}."
                    ),
                    "rationale": (
                        "Extends a product with existing sales history."
                    ),
                },
            ]
        )
    for candidate in candidates:
        candidate["category_id"] = category_id
        candidate["niche_id"] = niche_id
    return candidates


def _generate_candidates(
    snapshot: dict[str, Any],
    blocked: list[str],
    count: int,
) -> list[dict[str, Any]]:
    templates = _candidate_templates(snapshot)
    if not templates:
        raise RecommendationGenerationError(
            "No niche or sales history is available for this store."
        )
    selected: list[dict[str, Any]] = []
    seen = list(blocked)
    attempt = 0
    while len(selected) < count and attempt < max(50, count * 10):
        template = templates[attempt % len(templates)]
        suffix = "" if attempt < len(templates) else f" {attempt // len(templates) + 1}"
        name = f"{template['name']}{suffix}"
        description = template["description"]
        if not _is_duplicate(name, description, seen):
            selected.append(
                {
                    "name": name,
                    "description": description,
                    "category_id": template["category_id"],
                    "niche_id": template["niche_id"],
                    "rationale": template["rationale"],
                }
            )
            seen.append(_normalized(f"{name} {description}"))
        attempt += 1
    if not selected:
        raise RecommendationGenerationError(
            "All generated ideas were duplicates of existing concepts or "
            "dismissed ideas."
        )
    return selected


def create_generation_run(
    session: Session,
    tenant: TenantContext,
    requested_count: object = 3,
) -> dict[str, Any]:
    if (
        isinstance(requested_count, bool)
        or not isinstance(requested_count, int)
        or requested_count < 1
        or requested_count > MAX_REQUESTED_IDEAS
    ):
        raise RecommendationValidationError(
            f"requested_count must be between 1 and {MAX_REQUESTED_IDEAS}"
        )
    row = GenerationRunRepository(session).insert_run(
        {
            "requested_by": tenant.user_id,
            "model_version": MODEL_VERSION,
            "input_snapshot": Jsonb(
                {"schema_version": 1, "status": "pending"}
            ),
            "requested_count": requested_count,
            "returned_count": 0,
            "status": "queued",
        }
    )
    return _run_out(dict(row))


def _safe_error_message(exc: Exception) -> str:
    if isinstance(
        exc,
        (
            RecommendationGenerationError,
            RecommendationValidationError,
            RecommendationNotFound,
        ),
    ):
        return (str(exc).strip() or "Recommendation generation failed.")[:500]
    return "Recommendation generation failed."


def run_generation(
    session: Session,
    tenant: TenantContext,
    run_id: uuid.UUID | str,
) -> dict[str, Any]:
    repository = GenerationRunRepository(session)
    try:
        run = repository.get_for_update(run_id)
    except ValueError as exc:
        raise RecommendationNotFound("Generation run not found") from exc
    if run is None:
        raise RecommendationNotFound("Generation run not found")
    if run["status"] == "succeeded":
        return _run_out(dict(run))

    now = datetime.now(timezone.utc)
    repository.update_run(
        run_id,
        {"status": "running", "started_at": now, "error_message": None},
    )
    try:
        snapshot = _snapshot(session, tenant, int(run["requested_count"]))
        idea_repository = ProductIdeaRepository(session)
        blocked = _existing_names(session, tenant)
        blocked.extend(
            _normalized(f"{row['name']} {row['description']}")
            for row in idea_repository.dedupe_rows()
        )
        candidates = _generate_candidates(
            snapshot, blocked, int(run["requested_count"])
        )
        evidence_repository = IdeaEvidenceRepository(session)
        inserted = 0
        with session.begin_nested():
            for candidate in candidates:
                idea = idea_repository.insert_idea(
                    {
                        "generation_run_id": run["id"],
                        "name": candidate["name"],
                        "description": candidate["description"],
                        "category_id": candidate["category_id"],
                        "niche_id": candidate["niche_id"],
                        "rationale": candidate["rationale"],
                        "state": "new",
                        "model_version": MODEL_VERSION,
                    }
                )
                evidence_repository.insert_evidence(
                    {
                        "product_idea_id": idea["id"],
                        "evidence_type": "hypothesis",
                        "claim": candidate["rationale"],
                        "source_name": "Rules-based generation",
                        "source_url": None,
                        "source_published_at": None,
                        "retrieved_at": datetime.now(timezone.utc),
                        "confidence": 0.5,
                    }
                )
                blocked.append(
                    _normalized(
                        f"{candidate['name']} {candidate['description']}"
                    )
                )
                inserted += 1
        updated = repository.update_run(
            run_id,
            {
                "status": "succeeded",
                "input_snapshot": Jsonb(snapshot),
                "returned_count": inserted,
                "finished_at": datetime.now(timezone.utc),
                "error_message": None,
            },
        )
        return _run_out(dict(updated))
    except Exception as exc:
        logger.exception(
            "recommendation_generation_failed",
            extra={"run_id": str(run_id)},
        )
        raise RecommendationGenerationError(
            _safe_error_message(exc)
        ) from exc


def mark_generation_failed(
    session: Session,
    tenant: TenantContext,
    run_id: uuid.UUID | str,
    message: str,
) -> None:
    repository = GenerationRunRepository(session)
    try:
        run = repository.get_for_update(run_id)
    except ValueError:
        return
    if run is None or run["status"] == "succeeded":
        return
    repository.update_run(
        run_id,
        {
            "status": "failed",
            "error_message": (message or "Recommendation generation failed.")[
                :500
            ],
            "finished_at": datetime.now(timezone.utc),
        },
    )

def get_generation_run(
    session: Session,
    tenant: TenantContext,
    run_id: uuid.UUID | str,
) -> dict[str, Any]:
    try:
        row = GenerationRunRepository(session).get(run_id)
    except ValueError as exc:
        raise RecommendationNotFound("Generation run not found") from exc
    if row is None:
        raise RecommendationNotFound("Generation run not found")
    return _run_out(dict(row))


def list_generation_runs(
    session: Session,
    tenant: TenantContext,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    rows = GenerationRunRepository(session).list_runs(
        limit=limit, offset=offset
    )
    return [_run_out(dict(row)) for row in rows]


def get_ideas(
    session: Session,
    tenant: TenantContext,
    *,
    state: str | None = None,
    category_id: uuid.UUID | str | None = None,
    niche_id: uuid.UUID | str | None = None,
    generation_run_id: uuid.UUID | str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    if state is not None and state not in IDEA_STATES:
        raise RecommendationValidationError(
            "state must be new, saved, dismissed, or converted"
        )
    parsed: dict[str, uuid.UUID | None] = {}
    for name, value in (
        ("category_id", category_id),
        ("niche_id", niche_id),
        ("generation_run_id", generation_run_id),
    ):
        if value is None:
            parsed[name] = None
            continue
        try:
            parsed[name] = uuid.UUID(str(value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise RecommendationValidationError(
                f"{name} must be a valid UUID"
            ) from exc
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
        raise RecommendationValidationError(
            "limit must be an integer between 1 and 500"
        )
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise RecommendationValidationError(
            "offset must be a non-negative integer"
        )
    rows = ProductIdeaRepository(session).list_ideas(
        state=state,
        category_id=parsed["category_id"],
        niche_id=parsed["niche_id"],
        generation_run_id=parsed["generation_run_id"],
        limit=limit,
        offset=offset,
    )
    idea_ids = [row["id"] for row in rows]
    evidence_rows = IdeaEvidenceRepository(session).list_for_ideas(idea_ids)
    grouped: dict[uuid.UUID, list[Mapping[str, Any]]] = {
        idea_id: [] for idea_id in idea_ids
    }
    for evidence in evidence_rows:
        grouped.setdefault(evidence["product_idea_id"], []).append(evidence)
    freshness_days = get_settings().evidence_freshness_days
    return [
        _idea_out(
            dict(row),
            grouped.get(row["id"], []),
            freshness_days=freshness_days,
        )
        for row in rows
    ]


def get_idea(
    session: Session,
    tenant: TenantContext,
    idea_id: uuid.UUID | str,
) -> dict[str, Any]:
    try:
        row = ProductIdeaRepository(session).get_idea(idea_id)
    except ValueError as exc:
        raise RecommendationNotFound("Product idea not found") from exc
    if row is None:
        raise RecommendationNotFound("Product idea not found")
    evidence = IdeaEvidenceRepository(session).list_for_idea(idea_id)
    return _idea_out(
        dict(row),
        evidence,
        freshness_days=get_settings().evidence_freshness_days,
    )


def _idea_row(
    session: Session,
    idea_id: uuid.UUID | str,
) -> Mapping[str, Any]:
    try:
        row = ProductIdeaRepository(session).get_idea(idea_id)
    except ValueError as exc:
        raise RecommendationNotFound("Product idea not found") from exc
    if row is None:
        raise RecommendationNotFound("Product idea not found")
    return row


def _dismiss_reason(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RecommendationValidationError("reason must be a string")
    reason = value.strip()
    if len(reason) > 500:
        raise RecommendationValidationError(
            "reason must be 500 characters or fewer"
        )
    return reason or None


def save_idea(
    session: Session,
    tenant: TenantContext,
    idea_id: uuid.UUID | str,
    *,
    correlation_id: object = None,
) -> dict[str, Any]:
    row = _idea_row(session, idea_id)
    if row["state"] == "converted":
        raise RecommendationValidationError(
            "Converted ideas cannot be saved"
        )
    if row["state"] == "saved":
        return get_idea(session, tenant, idea_id)
    if row["state"] == "dismissed":
        raise RecommendationValidationError(
            "Dismissed ideas must be restored before saving"
        )
    repository = ProductIdeaRepository(session)
    updated = repository.update_idea(
        idea_id,
        {"state": "saved", "dismissed_reason": None},
    )
    if updated is None:
        raise RecommendationNotFound("Product idea not found")
    AuditService(session, tenant, correlation_id=correlation_id).record(
        action="product_idea.saved",
        target_type="product_idea",
        target_id=idea_id,
        before={"state": row["state"]},
        after={"state": "saved"},
    )
    return get_idea(session, tenant, idea_id)


def dismiss_idea(
    session: Session,
    tenant: TenantContext,
    idea_id: uuid.UUID | str,
    reason: object = None,
    *,
    correlation_id: object = None,
) -> dict[str, Any]:
    row = _idea_row(session, idea_id)
    if row["state"] == "converted":
        raise RecommendationValidationError(
            "Converted ideas cannot be dismissed"
        )
    parsed_reason = _dismiss_reason(reason)
    if row["state"] == "dismissed":
        if parsed_reason is not None and parsed_reason != row["dismissed_reason"]:
            updated = ProductIdeaRepository(session).update_idea(
                idea_id, {"dismissed_reason": parsed_reason}
            )
            if updated is None:
                raise RecommendationNotFound("Product idea not found")
            AuditService(
                session, tenant, correlation_id=correlation_id
            ).record(
                action="product_idea.dismissed",
                target_type="product_idea",
                target_id=idea_id,
                before={
                    "state": "dismissed",
                    "dismissed_reason": row["dismissed_reason"],
                },
                after={
                    "state": "dismissed",
                    "dismissed_reason": parsed_reason,
                },
            )
        return get_idea(session, tenant, idea_id)

    updated = ProductIdeaRepository(session).update_idea(
        idea_id,
        {"state": "dismissed", "dismissed_reason": parsed_reason},
    )
    if updated is None:
        raise RecommendationNotFound("Product idea not found")
    AuditService(session, tenant, correlation_id=correlation_id).record(
        action="product_idea.dismissed",
        target_type="product_idea",
        target_id=idea_id,
        before={"state": row["state"]},
        after={
            "state": "dismissed",
            "dismissed_reason": parsed_reason,
        },
    )
    return get_idea(session, tenant, idea_id)


def restore_idea(
    session: Session,
    tenant: TenantContext,
    idea_id: uuid.UUID | str,
    *,
    correlation_id: object = None,
) -> dict[str, Any]:
    row = _idea_row(session, idea_id)
    if row["state"] != "dismissed":
        raise RecommendationValidationError(
            "Only dismissed ideas can be restored"
        )
    updated = ProductIdeaRepository(session).update_idea(
        idea_id,
        {"state": "new", "dismissed_reason": None},
    )
    if updated is None:
        raise RecommendationNotFound("Product idea not found")
    AuditService(session, tenant, correlation_id=correlation_id).record(
        action="product_idea.restored",
        target_type="product_idea",
        target_id=idea_id,
        before={
            "state": "dismissed",
            "dismissed_reason": row["dismissed_reason"],
        },
        after={"state": "new", "dismissed_reason": None},
    )
    return get_idea(session, tenant, idea_id)


__all__ = [
    "IDEA_STATES",
    "MAX_REQUESTED_IDEAS",
    "MODEL_VERSION",
    "RecommendationError",
    "RecommendationGenerationError",
    "RecommendationNotFound",
    "RecommendationValidationError",
    "create_generation_run",
    "dismiss_idea",
    "get_generation_run",
    "get_idea",
    "get_ideas",
    "list_generation_runs",
    "mark_generation_failed",
    "restore_idea",
    "run_generation",
    "save_idea",
]

