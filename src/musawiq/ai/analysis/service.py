"""Validate AI analysis output against the fixed schema and supplied signals."""

from __future__ import annotations

from pydantic import ValidationError

from musawiq.ai.analysis.schema import AnalysisResult

TOLERANCE = 0.01


class AnalysisValidationError(ValueError):
    """Raised when analysis output is malformed or unsupported by evidence."""


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


__all__ = ["AnalysisValidationError", "TOLERANCE", "validate_result"]
