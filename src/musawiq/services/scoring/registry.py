"""Versioned scoring model registration and resolution."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.domain.scoring import (
    DEFAULT_MARGIN_CEILING_BP,
    DEFAULT_MARGIN_FLOOR_BP,
    DEFAULT_MODEL_DESCRIPTION,
    DEFAULT_MODEL_KEY,
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_VERSION,
    DEFAULT_PARAMETERS,
    DEFAULT_SCORE_SCALE,
    DEFAULT_WEIGHTS,
)
from musawiq.repositories.scoring_models import ScoringModelRepository
from musawiq.services.scoring.strategy import (
    ScoringStrategyError,
    validate_model_definition,
)


class ScoringModelError(Exception):
    """Base class for scoring model contract failures."""


class ScoringModelNotFound(ScoringModelError):
    """Raised when the requested model is not visible to the store."""


class ScoringModelValidationError(ScoringModelError):
    """Raised when a model definition is invalid."""


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScoringModelValidationError(f"{field} is required")
    return value.strip()


def _version(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 1
    ):
        raise ScoringModelValidationError(
            "version must be a positive integer"
        )
    return value


def _effective_from(value: object) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ScoringModelValidationError(
                "effective_from must be an ISO datetime"
            ) from exc
    else:
        raise ScoringModelValidationError(
            "effective_from must be an ISO datetime"
        )
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def create_scoring_model(
    session: Session,
    tenant: TenantContext,
    payload: Mapping[str, Any],
    *,
    platform: bool = False,
) -> Mapping[str, Any]:
    """Register a new immutable model version."""

    key = _required_text(payload.get("key"), "key")
    version = _version(payload.get("version"))
    name = _required_text(payload.get("name"), "name")
    description = payload.get("description")
    if description is not None and not isinstance(description, str):
        raise ScoringModelValidationError("description must be a string")
    weights = payload.get("weights")
    parameters = payload.get("parameters", {})
    model_definition = {
        "weights": weights,
        "parameters": parameters,
    }
    try:
        validate_model_definition(model_definition)
    except ScoringStrategyError as exc:
        raise ScoringModelValidationError(str(exc)) from exc

    is_active = payload.get("is_active", True)
    if not isinstance(is_active, bool):
        raise ScoringModelValidationError("is_active must be a boolean")
    effective_from = _effective_from(payload.get("effective_from"))

    repository = ScoringModelRepository(session)
    if repository.get_by_key_version(key, version) is not None:
        raise ScoringModelValidationError(
            "key and version must be unique"
        )
    try:
        return repository.insert(
            {
                "store_id": None if platform else tenant.store_id,
                "key": key,
                "version": version,
                "name": name,
                "description": description,
                "weights": Jsonb(weights),
                "parameters": Jsonb(parameters),
                "is_active": is_active,
                "effective_from": effective_from,
            }
        )
    except IntegrityError as exc:
        raise ScoringModelValidationError(
            "key and version must be unique"
        ) from exc


def ensure_default_model(
    session: Session, tenant: TenantContext
) -> Mapping[str, Any]:
    """Return the platform default model, creating v1 when needed."""

    repository = ScoringModelRepository(session)
    existing = repository.get_by_key_version(
        DEFAULT_MODEL_KEY, DEFAULT_MODEL_VERSION
    )
    if existing is not None:
        return existing
    try:
        return repository.insert(
            {
                "store_id": None,
                "key": DEFAULT_MODEL_KEY,
                "version": DEFAULT_MODEL_VERSION,
                "name": DEFAULT_MODEL_NAME,
                "description": DEFAULT_MODEL_DESCRIPTION,
                "weights": Jsonb(DEFAULT_WEIGHTS),
                "parameters": Jsonb(DEFAULT_PARAMETERS),
                "is_active": True,
                "effective_from": datetime.now(timezone.utc),
            }
        )
    except IntegrityError:
        existing = repository.get_by_key_version(
            DEFAULT_MODEL_KEY, DEFAULT_MODEL_VERSION
        )
        if existing is None:
            raise
        return existing


def resolve_scoring_model(
    session: Session,
    tenant: TenantContext,
    model_id: uuid.UUID | str | None = None,
) -> Mapping[str, Any]:
    """Resolve an explicit model or the store/platform default."""

    repository = ScoringModelRepository(session)
    if model_id is not None:
        try:
            row = repository.get_visible(model_id, tenant.store_id)
        except ValueError as exc:
            raise ScoringModelNotFound("Scoring model not found") from exc
        if row is None:
            raise ScoringModelNotFound("Scoring model not found")
        return row

    row = repository.active_for_store(tenant.store_id)
    if row is None:
        row = repository.platform_default()
    if row is None:
        row = ensure_default_model(session, tenant)
    return row


def list_scoring_models(
    session: Session, tenant: TenantContext
) -> list[Mapping[str, Any]]:
    return ScoringModelRepository(session).list_visible(tenant.store_id)


__all__ = [
    "ScoringModelError",
    "ScoringModelNotFound",
    "ScoringModelValidationError",
    "create_scoring_model",
    "ensure_default_model",
    "list_scoring_models",
    "resolve_scoring_model",
]
