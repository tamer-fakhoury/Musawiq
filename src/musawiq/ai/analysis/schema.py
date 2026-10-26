"""Fixed schema for one AI demand and issue analysis."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DemandLevel = Literal["strong", "moderate", "weak", "inconclusive"]
IssueType = Literal["content", "channel", "targeting", "budget", "audience"]
Severity = Literal["low", "medium", "high"]
Action = Literal[
    "keep",
    "pause",
    "increase_budget",
    "decrease_budget",
    "change_copy",
    "change_creative",
    "change_targeting",
]


class Demand(BaseModel):
    level: DemandLevel
    confidence: float = Field(ge=0, le=1)
    rationale_ar: str


class Issue(BaseModel):
    type: IssueType
    severity: Severity
    metric: str
    observed: float
    benchmark: float | str
    rationale_ar: str


class Recommendation(BaseModel):
    action: Action
    target: str
    change_ar: str
    expected_impact_ar: str
    confidence: float = Field(ge=0, le=1)
    copy_paste_ar: str


class AnalysisResult(BaseModel):
    demand: Demand
    issues: list[Issue]
    recommendations: list[Recommendation]
    next_steps_ar: list[str]
    delta: dict[str, Any] | None = None


__all__ = [
    "Action",
    "AnalysisResult",
    "Demand",
    "DemandLevel",
    "Issue",
    "IssueType",
    "Recommendation",
    "Severity",
]
