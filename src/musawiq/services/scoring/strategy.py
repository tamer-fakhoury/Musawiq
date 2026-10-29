"""Deterministic rules-based weighted scoring strategy (v1)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from musawiq.domain.scoring import (
    DEFAULT_FACTOR_DEFINITIONS,
    DEFAULT_MARGIN_CEILING_BP,
    DEFAULT_MARGIN_FLOOR_BP,
    DEFAULT_SCORE_SCALE,
    DEFAULT_STATUS_VALUES,
    EvaluationResult,
    FactorContribution,
)

_SUPPORTED_FACTORS = frozenset(DEFAULT_FACTOR_DEFINITIONS)


class ScoringStrategyError(ValueError):
    """Raised when a scoring model cannot be applied."""


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScoringStrategyError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ScoringStrategyError(f"{name} must be finite")
    return result


def validate_model_definition(
    model: Mapping[str, Any],
) -> tuple[dict[str, float], Mapping[str, Any], int]:
    weights = model.get("weights")
    parameters = model.get("parameters") or {}
    if not isinstance(weights, Mapping) or not weights:
        raise ScoringStrategyError("weights must be a non-empty object")
    if not isinstance(parameters, Mapping):
        raise ScoringStrategyError("parameters must be an object")

    normalized_weights: dict[str, float] = {}
    for key, value in weights.items():
        if not isinstance(key, str) or key not in _SUPPORTED_FACTORS:
            raise ScoringStrategyError(f"unsupported factor {key!r}")
        normalized_weights[key] = _number(value, f"weights.{key}")
        if normalized_weights[key] < 0:
            raise ScoringStrategyError(f"weights.{key} must not be negative")
    if sum(normalized_weights.values()) <= 0:
        raise ScoringStrategyError("weights must sum to a positive value")

    factors = parameters.get("factors")
    if not isinstance(factors, Mapping) or not factors:
        raise ScoringStrategyError("parameters.factors must be defined")
    for key in normalized_weights:
        definition = factors.get(key)
        if not isinstance(definition, Mapping):
            raise ScoringStrategyError(
                f"missing factor definition for {key!r}"
            )
        if not isinstance(definition.get("label"), str) or not definition[
            "label"
        ].strip():
            raise ScoringStrategyError(
                f"factor {key!r} must define a label"
            )

    score_scale = parameters.get("score_scale", DEFAULT_SCORE_SCALE)
    if (
        isinstance(score_scale, bool)
        or not isinstance(score_scale, int)
        or score_scale < 1
        or score_scale > 10_000
    ):
        raise ScoringStrategyError(
            "parameters.score_scale must be an integer between 1 and 10000"
        )

    floor = parameters.get("margin_floor_bp", DEFAULT_MARGIN_FLOOR_BP)
    ceiling = parameters.get(
        "margin_ceiling_bp", DEFAULT_MARGIN_CEILING_BP
    )
    if (
        isinstance(floor, bool)
        or isinstance(ceiling, bool)
        or not isinstance(floor, int)
        or not isinstance(ceiling, int)
        or ceiling <= floor
    ):
        raise ScoringStrategyError(
            "margin_floor_bp and margin_ceiling_bp must be increasing integers"
        )
    return normalized_weights, parameters, score_scale


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _status_value(
    parameters: Mapping[str, Any],
    factor: str,
    status: str,
) -> float:
    configured = parameters.get("status_values")
    if isinstance(configured, Mapping):
        factor_values = configured.get(factor)
        if isinstance(factor_values, Mapping) and status in factor_values:
            return _number(factor_values[status], f"{factor}.{status}")
    return float(DEFAULT_STATUS_VALUES[factor].get(status, 0.0))


def _value_for(
    key: str,
    *,
    concept: Mapping[str, Any],
    sufficiency: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> float:
    if key == "margin":
        floor = int(parameters.get("margin_floor_bp", 0))
        ceiling = int(parameters.get("margin_ceiling_bp", 6000))
        margin_bp = int(concept.get("gross_margin_bp") or 0)
        return _clamp(
            (margin_bp - floor) / (ceiling - floor) * 100.0,
            0.0,
            100.0,
        )
    if key == "sales_history":
        return _status_value(
            parameters,
            "sales_history",
            str(sufficiency.get("sales_history_status", "missing")),
        )
    if key == "audience":
        return _status_value(
            parameters,
            "audience",
            str(sufficiency.get("audience_status", "missing")),
        )
    return _status_value(
        parameters,
        "competitive_data",
        str(sufficiency.get("competitive_data_status", "missing")),
    )


def _explanation(
    key: str,
    value: float,
    concept: Mapping[str, Any],
    sufficiency: Mapping[str, Any],
) -> str:
    if key == "margin":
        margin = int(concept.get("gross_margin_bp") or 0) / 100
        return (
            f"Gross margin of {margin:.1f}% maps to {value:.1f} of 100 "
            "for this factor."
        )
    if key == "sales_history":
        status = sufficiency.get("sales_history_status", "missing")
        return f"Sales history is {status}; factor value is {value:.1f}."
    if key == "audience":
        status = sufficiency.get("audience_status", "missing")
        return f"Audience data is {status}; factor value is {value:.1f}."
    status = sufficiency.get("competitive_data_status", "missing")
    return f"Competitive data is {status}; factor value is {value:.1f}."


class RulesBasedScoringStrategy:
    """Apply a versioned weighted model to a concept and input snapshot."""

    def score(
        self,
        concept: Mapping[str, Any],
        inputs: Mapping[str, Any],
        model: Mapping[str, Any],
    ) -> EvaluationResult:
        weights, parameters, score_scale = validate_model_definition(model)
        sufficiency = inputs.get("sufficiency")
        if not isinstance(sufficiency, Mapping):
            raise ScoringStrategyError(
                "inputs.sufficiency must be an object"
            )

        total_weight = sum(weights.values())
        factors_definition = parameters["factors"]
        factors: list[FactorContribution] = []
        weighted_points = 0.0
        for key, weight in weights.items():
            value = _value_for(
                key,
                concept=concept,
                sufficiency=sufficiency,
                parameters=parameters,
            )
            contribution = round(
                weight / total_weight * value * score_scale / 100.0,
                4,
            )
            weighted_points += contribution
            definition = factors_definition[key]
            direction = (
                "positive"
                if value > 50
                else "negative"
                if value < 50
                else "neutral"
            )
            status = (
                "measured"
                if definition.get("evidence_source") != "inferred"
                else "inferred"
            )
            factors.append(
                FactorContribution(
                    key=key,
                    label=str(definition["label"]),
                    direction=direction,
                    contribution=contribution,
                    explanation=_explanation(
                        key, value, concept, sufficiency
                    ),
                    evidence={
                        "schema_version": 1,
                        "source": status,
                        "factor_value": round(value, 4),
                    },
                )
            )

        overall = sufficiency.get("overall_status")
        reliable = overall == "sufficient"
        if not reliable:
            confidence = "low"
            score = None
        else:
            confidence = (
                "high"
                if sufficiency.get("competitive_data_status") == "available"
                else "medium"
            )
            score = round(
                _clamp(
                    weighted_points,
                    0.0,
                    float(score_scale),
                ),
                4,
            )
        return EvaluationResult(
            score=score,
            score_scale=score_scale,
            confidence=confidence,
            is_reliable=reliable,
            factors=tuple(factors),
        )


__all__ = [
    "RulesBasedScoringStrategy",
    "ScoringStrategyError",
    "validate_model_definition",
]
