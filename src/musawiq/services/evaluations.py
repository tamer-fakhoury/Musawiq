"""Viability evaluation, idempotency, and input snapshots."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.repositories.evaluations import EvaluationRepository
from musawiq.repositories.product_concepts import ProductConceptRepository
from musawiq.repositories.score_factors import ScoreFactorRepository
from musawiq.services.concepts import ConceptNotFound
from musawiq.services.scoring.registry import (
    ScoringModelValidationError,
    resolve_scoring_model,
)
from musawiq.services.scoring.strategy import (
    RulesBasedScoringStrategy,
    ScoringStrategyError,
)
from musawiq.services.sufficiency import run_sufficiency_check


class EvaluationError(Exception):
    """Base class for evaluation contract failures."""


class EvaluationNotFound(EvaluationError):
    """Raised when an evaluation does not belong to the active tenant."""


class EvaluationValidationError(EvaluationError):
    """Raised when an evaluation cannot be produced."""


def _iso(value: object) -> str | None:
    return value.isoformat() if value is not None else None


def _number(value: object) -> float | None:
    return float(value) if value is not None else None


def _factor_out(row: Mapping[str, Any]) -> dict[str, Any]:
    evidence = row["evidence"] if isinstance(row["evidence"], Mapping) else {}
    return {
        "id": str(row["id"]),
        "factor_key": row["factor_key"],
        "factor_label": row["factor_label"],
        "direction": row["direction"],
        "contribution": float(row["contribution"]),
        "explanation": row["explanation"],
        "evidence": dict(evidence),
    }


def _evaluation_out(
    row: Mapping[str, Any], factors: list[Mapping[str, Any]]
) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "store_id": str(row["store_id"]),
        "product_concept_id": str(row["product_concept_id"]),
        "scoring_model_id": str(row["scoring_model_id"]),
        "model_version": row["model_version"],
        "score": _number(row["score"]),
        "score_scale": row["score_scale"],
        "confidence": row["confidence"],
        "is_reliable": row["is_reliable"],
        "sufficiency_check_id": (
            str(row["sufficiency_check_id"])
            if row["sufficiency_check_id"] is not None
            else None
        ),
        "input_snapshot": row["input_snapshot"],
        "evaluated_at": _iso(row["evaluated_at"]),
        "created_at": _iso(row["created_at"]),
        "factors": [_factor_out(factor) for factor in factors],
    }


def _concept_row(
    session: Session, concept_id: uuid.UUID | str
) -> Mapping[str, Any]:
    try:
        row = ProductConceptRepository(session).get(concept_id)
    except ValueError as exc:
        raise ConceptNotFound("Product concept not found") from exc
    if row is None or row["deleted_at"] is not None:
        raise ConceptNotFound("Product concept not found")
    return row


def _input_snapshot(
    concept: Mapping[str, Any],
    sufficiency: Mapping[str, Any],
    model: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "concept": {
            "id": str(concept["id"]),
            "name": concept["name"],
            "description": concept["description"],
            "category_id": str(concept["category_id"]),
            "niche_id": (
                str(concept["niche_id"])
                if concept["niche_id"] is not None
                else None
            ),
            "price_minor": concept["price_minor"],
            "cost_minor": concept["cost_minor"],
            "currency": concept["currency"].strip(),
            "gross_margin_bp": concept["gross_margin_bp"],
        },
        "sufficiency": {
            "sales_history_status": sufficiency["sales_history_status"],
            "audience_status": sufficiency["audience_status"],
            "cost_price_status": sufficiency["cost_price_status"],
            "competitive_data_status": sufficiency[
                "competitive_data_status"
            ],
            "overall_status": sufficiency["overall_status"],
            "blocking_reasons": sufficiency["blocking_reasons"],
            "policy_version": sufficiency.get("policy_version"),
        },
        "model": {
            "key": model["key"],
            "version": model["version"],
            "weights": model["weights"],
            "parameters": model["parameters"],
        },
    }


def _existing_or_new(
    session: Session,
    concept: Mapping[str, Any],
    model: Mapping[str, Any],
    sufficiency: Mapping[str, Any],
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    repository = EvaluationRepository(session)
    snapshot = _input_snapshot(concept, sufficiency, model)
    existing = repository.find_idempotent(
        concept["id"],
        model["id"],
        int(model["version"]),
        snapshot,
    )
    if existing is not None:
        factors = ScoreFactorRepository(session).list_for_evaluation(
            existing["id"]
        )
        return existing, factors

    result = RulesBasedScoringStrategy().score(concept, snapshot, model)
    row = repository.insert_evaluation(
        {
            "product_concept_id": concept["id"],
            "scoring_model_id": model["id"],
            "model_version": int(model["version"]),
            "score": (
                Decimal(str(result.score))
                if result.score is not None
                else None
            ),
            "score_scale": result.score_scale,
            "confidence": result.confidence,
            "is_reliable": result.is_reliable,
            "sufficiency_check_id": sufficiency.get("id"),
            "input_snapshot": Jsonb(snapshot),
            "evaluated_at": datetime.now(timezone.utc),
        }
    )
    factor_repository = ScoreFactorRepository(session)
    for factor in result.factors:
        factor_repository.insert_factor(
            {
                "evaluation_id": row["id"],
                "factor_key": factor.key,
                "factor_label": factor.label,
                "direction": factor.direction,
                "contribution": Decimal(str(factor.contribution)),
                "explanation": factor.explanation,
                "evidence": Jsonb(factor.evidence),
            }
        )
    factors = factor_repository.list_for_evaluation(row["id"])
    return row, factors


def evaluate_concept(
    session: Session,
    tenant: TenantContext,
    concept_id: uuid.UUID | str,
    *,
    model_id: uuid.UUID | str | None = None,
) -> dict[str, Any]:
    """Evaluate one concept, reusing an identical prior evaluation."""

    concept = _concept_row(session, concept_id)
    try:
        model = resolve_scoring_model(session, tenant, model_id)
    except ScoringModelValidationError as exc:
        raise EvaluationValidationError(str(exc)) from exc

    sufficiency = run_sufficiency_check(session, tenant, concept_id)
    try:
        row, factors = _existing_or_new(
            session, concept, model, sufficiency
        )
    except ScoringStrategyError as exc:
        raise EvaluationValidationError(str(exc)) from exc

    if concept["status"] == "draft":
        updated = ProductConceptRepository(session).update_versioned(
            concept["id"],
            concept["version"],
            {
                "status": "evaluated",
                "version": concept["version"] + 1,
            },
        )
        if updated is None:
            raise EvaluationValidationError(
                "Concept changed during evaluation"
            )
    return _evaluation_out(row, factors)


def get_evaluation(
    session: Session,
    tenant: TenantContext,
    evaluation_id: uuid.UUID | str,
) -> dict[str, Any]:
    try:
        row = EvaluationRepository(session).get(evaluation_id)
    except ValueError as exc:
        raise EvaluationNotFound("Evaluation not found") from exc
    if row is None:
        raise EvaluationNotFound("Evaluation not found")
    factors = ScoreFactorRepository(session).list_for_evaluation(row["id"])
    return _evaluation_out(row, factors)


def get_latest_evaluation(
    session: Session,
    tenant: TenantContext,
    concept_id: uuid.UUID | str,
) -> dict[str, Any] | None:
    try:
        row = EvaluationRepository(session).latest_for_concept(concept_id)
    except ValueError as exc:
        raise EvaluationNotFound("Evaluation not found") from exc
    if row is None:
        return None
    factors = ScoreFactorRepository(session).list_for_evaluation(row["id"])
    return _evaluation_out(row, factors)


__all__ = [
    "EvaluationError",
    "EvaluationNotFound",
    "EvaluationValidationError",
    "evaluate_concept",
    "get_evaluation",
    "get_latest_evaluation",
]
