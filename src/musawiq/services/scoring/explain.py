"""Score explanation, limitations, and measured-versus-inferred labeling."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.repositories.sufficiency_checks import SufficiencyCheckRepository
from musawiq.services.evaluations import get_evaluation

GUARANTEE_PHRASES = (
    "guarantee",
    "guaranteed",
    "promise",
    "will sell",
    "ensure sales",
    "risk-free",
)

_INPUT_LABELS = {
    "sales_history": "Sales history",
    "audience": "Audience data",
    "cost_price": "Price and cost",
    "competitive_data": "Competitive data",
}
_STAT_FIELDS = {
    "sales_history": "sales_history_status",
    "audience": "audience_status",
    "cost_price": "cost_price_status",
    "competitive_data": "competitive_data_status",
}


class ExplanationNotFound(Exception):
    """Raised when an evaluation or its context is missing."""


def contains_guarantee_language(value: str) -> bool:
    lowered = value.lower()
    return any(phrase in lowered for phrase in GUARANTEE_PHRASES)


def _safe_copy(value: str) -> str:
    if contains_guarantee_language(value):
        raise ValueError("score copy contains guarantee-of-sales language")
    return value


def _limitations(check: Mapping[str, Any] | None) -> list[str]:
    if check is None:
        return ["The matching sufficiency check is unavailable."]
    limitations = []
    for key, field in _STAT_FIELDS.items():
        status = check[field]
        if status != "available":
            limitations.append(f"{_INPUT_LABELS[key]} is {status}.")
    return limitations


def _factor_view(factor: Mapping[str, Any]) -> dict[str, Any]:
    evidence = factor["evidence"]
    source = evidence.get("source", "measured")
    return {
        "factor_key": factor["factor_key"],
        "factor_label": factor["factor_label"],
        "direction": factor["direction"],
        "contribution": factor["contribution"],
        "explanation": _safe_copy(factor["explanation"]),
        "evidence": evidence,
        "evidence_label": source,
    }


def explain_evaluation(
    session: Session,
    tenant: TenantContext,
    evaluation_id: uuid.UUID | str,
) -> dict[str, Any]:
    """Return top contributors, confidence, limitations, and provenance."""

    evaluation = get_evaluation(session, tenant, evaluation_id)
    check = None
    if evaluation["sufficiency_check_id"] is not None:
        check = SufficiencyCheckRepository(session).get_check(
            evaluation["sufficiency_check_id"]
        )

    factors = [_factor_view(factor) for factor in evaluation["factors"]]
    positives = [
        factor for factor in factors if factor["direction"] == "positive"
    ][:3]
    negatives = [
        factor for factor in factors if factor["direction"] == "negative"
    ][:3]
    measured = sorted(
        {
            factor["factor_key"]
            for factor in factors
            if factor["evidence_label"] == "measured"
        }
    )
    inferred = sorted(
        {
            factor["factor_key"]
            for factor in factors
            if factor["evidence_label"] == "inferred"
        }
    )
    limitations = _limitations(check)
    score = evaluation["score"]
    if score is None:
        summary = (
            "Score is unavailable because critical inputs are missing or "
            "insufficient."
        )
    else:
        summary = (
            f"Score {score:.1f} of {evaluation['score_scale']} with "
            f"{evaluation['confidence']} confidence."
        )

    return {
        "evaluation_id": evaluation["id"],
        "product_concept_id": evaluation["product_concept_id"],
        "score": score,
        "score_scale": evaluation["score_scale"],
        "confidence": evaluation["confidence"],
        "is_reliable": evaluation["is_reliable"],
        "summary": _safe_copy(summary),
        "top_positive": positives,
        "top_negative": negatives,
        "factors": factors,
        "limitations": limitations,
        "measured_inputs": measured,
        "inferred_inputs": inferred,
        "sufficiency_check": (
            {
                "id": str(check["id"]),
                "overall_status": check["overall_status"],
                "blocking_reasons": check["blocking_reasons"],
                "checked_at": check["checked_at"].isoformat(),
            }
            if check is not None
            else None
        ),
    }


__all__ = [
    "ExplanationNotFound",
    "GUARANTEE_PHRASES",
    "contains_guarantee_language",
    "explain_evaluation",
]
