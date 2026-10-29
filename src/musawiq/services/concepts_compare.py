"""Concept comparison, selection, and Stage 2 handoff."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.repositories.evaluations import EvaluationRepository
from musawiq.repositories.product_concepts import ProductConceptRepository
from musawiq.repositories.score_factors import ScoreFactorRepository
from musawiq.services.audit import AuditService
from musawiq.services.concepts import (
    ConceptConflict,
    ConceptNotFound,
    ConceptValidationError,
    get_concept,
)

MAX_COMPARE_CONCEPTS = 20
MAX_SELECT_CONCEPTS = 100


def _concept_ids(values: object, *, maximum: int) -> list[uuid.UUID]:
    if not isinstance(values, (list, tuple)) or not values:
        raise ConceptValidationError(
            {"concept_ids": "concept_ids must be a non-empty list"}
        )
    if len(values) > maximum:
        raise ConceptValidationError(
            {
                "concept_ids": (
                    f"concept_ids must contain at most {maximum} concepts"
                )
            }
        )
    result: list[uuid.UUID] = []
    for value in values:
        try:
            parsed = uuid.UUID(str(value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ConceptValidationError(
                {"concept_ids": "concept_ids must contain valid UUIDs"}
            ) from exc
        if parsed not in result:
            result.append(parsed)
    return result


def _category_name(
    session: Session, tenant: TenantContext, category_id: object
) -> str | None:
    row = session.execute(
        text(
            """
            SELECT name FROM categories
            WHERE id = :id
            """
        ),
        {"id": category_id},
    ).first()
    return row[0] if row is not None else None


def _factor_view(row: Mapping[str, Any]) -> dict[str, Any]:
    evidence = row["evidence"] if isinstance(row["evidence"], Mapping) else {}
    return {
        "factor_key": row["factor_key"],
        "factor_label": row["factor_label"],
        "direction": row["direction"],
        "contribution": float(row["contribution"]),
        "explanation": row["explanation"],
        "evidence": dict(evidence),
    }


def compare_concepts(
    session: Session,
    tenant: TenantContext,
    concept_ids: object,
) -> dict[str, Any]:
    """Return side-by-side metrics for evaluated, store-owned concepts."""

    ids = _concept_ids(concept_ids, maximum=MAX_COMPARE_CONCEPTS)
    concepts = ProductConceptRepository(session)
    evaluations = EvaluationRepository(session)
    factors = ScoreFactorRepository(session)

    result = []
    for concept_id in ids:
        concept = concepts.get(concept_id)
        if concept is None or concept["deleted_at"] is not None:
            raise ConceptNotFound("Product concept not found")
        if concept["status"] not in {"evaluated", "selected"}:
            raise ConceptConflict(
                "Only evaluated concepts can be compared"
            )
        evaluation = evaluations.latest_for_concept(concept_id)
        if evaluation is None:
            raise ConceptConflict("Concept has no evaluation")
        factor_rows = factors.list_for_evaluation(evaluation["id"])[:3]
        result.append(
            {
                "concept_id": str(concept["id"]),
                "name": concept["name"],
                "status": concept["status"],
                "category_id": str(concept["category_id"]),
                "category": _category_name(
                    session, tenant, concept["category_id"]
                ),
                "price_minor": concept["price_minor"],
                "cost_minor": concept["cost_minor"],
                "currency": concept["currency"].strip(),
                "gross_margin_bp": concept["gross_margin_bp"],
                "gross_margin_percent": int(
                    concept["gross_margin_bp"]
                ) / 100,
                "evaluation_id": str(evaluation["id"]),
                "score": (
                    float(evaluation["score"])
                    if evaluation["score"] is not None
                    else None
                ),
                "score_scale": evaluation["score_scale"],
                "confidence": evaluation["confidence"],
                "is_reliable": evaluation["is_reliable"],
                "evaluated_at": evaluation["evaluated_at"].isoformat(),
                "top_factors": [
                    _factor_view(row) for row in factor_rows
                ],
            }
        )
    return {"concepts": result, "count": len(result)}


def select_concepts(
    session: Session,
    tenant: TenantContext,
    concept_ids: object,
    *,
    correlation_id: object = None,
) -> dict[str, Any]:
    """Move evaluated concepts to selected and audit each transition."""

    ids = _concept_ids(concept_ids, maximum=MAX_SELECT_CONCEPTS)
    repository = ProductConceptRepository(session)
    rows = repository.get_many_for_update(ids)
    ordered = []
    for concept_id in ids:
        row = rows.get(concept_id)
        if row is None:
            raise ConceptNotFound("Product concept not found")
        if row["status"] == "archived":
            raise ConceptConflict("Archived concepts cannot be selected")
        if row["status"] not in {"evaluated", "selected"}:
            raise ConceptConflict(
                "Only evaluated concepts can be selected"
            )
        if not repository.has_evaluation(concept_id):
            raise ConceptConflict("Concept has no evaluation")
        ordered.append(row)

    audit = AuditService(
        session, tenant, correlation_id=correlation_id
    )
    selected_ids: list[str] = []
    for row in ordered:
        if row["status"] != "selected":
            updated = repository.update_versioned(
                row["id"],
                row["version"],
                {
                    "status": "selected",
                    "version": row["version"] + 1,
                },
            )
            if updated is None:
                raise ConceptConflict("Concept version is stale")
            audit.record(
                action="product_concept.selected",
                target_type="product_concept",
                target_id=row["id"],
                before={
                    "status": row["status"],
                    "version": row["version"],
                },
                after={
                    "status": "selected",
                    "version": updated["version"],
                },
                metadata={"selection_batch_size": len(ordered)},
            )
        selected_ids.append(str(row["id"]))

    return {
        "selected_ids": selected_ids,
        "concepts": [
            get_concept(session, tenant, concept_id)
            for concept_id in ids
        ],
    }


__all__ = [
    "MAX_COMPARE_CONCEPTS",
    "MAX_SELECT_CONCEPTS",
    "compare_concepts",
    "select_concepts",
]
