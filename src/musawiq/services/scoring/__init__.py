"""Versioned scoring models and deterministic rules-based strategy."""

from musawiq.services.scoring.registry import (
    ScoringModelError,
    ScoringModelNotFound,
    ScoringModelValidationError,
    create_scoring_model,
    ensure_default_model,
    list_scoring_models,
    resolve_scoring_model,
)
from musawiq.services.scoring.strategy import (
    RulesBasedScoringStrategy,
    ScoringStrategyError,
    validate_model_definition,
)

__all__ = [
    "RulesBasedScoringStrategy",
    "ScoringModelError",
    "ScoringModelNotFound",
    "ScoringModelValidationError",
    "ScoringStrategyError",
    "create_scoring_model",
    "ensure_default_model",
    "list_scoring_models",
    "resolve_scoring_model",
    "validate_model_definition",
]
