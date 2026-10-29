"""Rules-based scoring model defaults and result value objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_MODEL_KEY = "rules_v1"
DEFAULT_MODEL_VERSION = 1
DEFAULT_SCORE_SCALE = 100
DEFAULT_MARGIN_FLOOR_BP = 0
DEFAULT_MARGIN_CEILING_BP = 6000

DEFAULT_WEIGHTS = {
    "margin": 0.40,
    "sales_history": 0.25,
    "audience": 0.20,
    "competitive_data": 0.15,
}

DEFAULT_FACTOR_DEFINITIONS = {
    "margin": {
        "label": "Gross margin",
        "description": "Gross margin mapped from 0% to 60%.",
        "evidence_source": "measured",
    },
    "sales_history": {
        "label": "Sales history",
        "description": "Availability and freshness of qualifying orders.",
        "evidence_source": "measured",
    },
    "audience": {
        "label": "Audience completeness",
        "description": "Completeness and freshness of the current audience profile.",
        "evidence_source": "measured",
    },
    "competitive_data": {
        "label": "Competitive data",
        "description": "Optional competitive-data availability.",
        "evidence_source": "inferred",
    },
}

DEFAULT_STATUS_VALUES = {
    "sales_history": {
        "available": 100.0,
        "stale": 40.0,
        "insufficient": 20.0,
        "missing": 0.0,
    },
    "audience": {
        "available": 100.0,
        "stale": 50.0,
        "insufficient": 25.0,
        "missing": 0.0,
    },
    "competitive_data": {
        "available": 100.0,
        "stale": 50.0,
        "insufficient": 25.0,
        "missing": 50.0,
    },
}

DEFAULT_PARAMETERS = {
    "schema_version": 1,
    "score_scale": DEFAULT_SCORE_SCALE,
    "margin_floor_bp": DEFAULT_MARGIN_FLOOR_BP,
    "margin_ceiling_bp": DEFAULT_MARGIN_CEILING_BP,
    "factors": DEFAULT_FACTOR_DEFINITIONS,
    "status_values": DEFAULT_STATUS_VALUES,
}

DEFAULT_MODEL_NAME = "Rules-based viability v1"
DEFAULT_MODEL_DESCRIPTION = (
    "Deterministic weighted model using margin, sales history, audience "
    "completeness, and optional competitive data."
)


@dataclass(frozen=True, slots=True)
class FactorContribution:
    key: str
    label: str
    direction: str
    contribution: float
    explanation: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    score: float | None
    score_scale: int
    confidence: str
    is_reliable: bool
    factors: tuple[FactorContribution, ...]


__all__ = [
    "DEFAULT_FACTOR_DEFINITIONS",
    "DEFAULT_MARGIN_CEILING_BP",
    "DEFAULT_MARGIN_FLOOR_BP",
    "DEFAULT_MODEL_DESCRIPTION",
    "DEFAULT_MODEL_KEY",
    "DEFAULT_MODEL_NAME",
    "DEFAULT_MODEL_VERSION",
    "DEFAULT_PARAMETERS",
    "DEFAULT_SCORE_SCALE",
    "DEFAULT_STATUS_VALUES",
    "DEFAULT_WEIGHTS",
    "EvaluationResult",
    "FactorContribution",
]
