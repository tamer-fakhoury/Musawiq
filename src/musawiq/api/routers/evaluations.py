"""Viability evaluation and explanation HTTP endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.jobs.queue import (
    IdempotencyConflict,
    InvalidJobType,
    enqueue,
)
from musawiq.middleware.correlation import get_correlation_id, uuid7
from musawiq.middleware.errors import error_response
from musawiq.services.concepts import ConceptNotFound
from musawiq.services.evaluations import (
    EvaluationNotFound,
    EvaluationValidationError,
    evaluate_concept,
    get_evaluation,
    get_latest_evaluation,
)
from musawiq.services.scoring.explain import (
    ExplanationNotFound,
    explain_evaluation,
)
from musawiq.services.scoring.registry import ScoringModelNotFound

router = APIRouter(tags=["evaluations"])


class EvaluateRequest(BaseModel):
    model_id: uuid.UUID | None = None


class BatchEvaluateRequest(BaseModel):
    concept_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    model_id: uuid.UUID | None = None


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


def _not_found(request: Request, message: str):
    return error_response(
        request,
        status_code=404,
        code="not_found",
        message=message,
    )


def _validation(request: Request, message: str):
    return error_response(
        request,
        status_code=422,
        code="validation_error",
        message=message,
    )


def _request_correlation_id(request: Request) -> str:
    value = getattr(request.state, "correlation_id", None)
    if not value:
        value = get_correlation_id()
    if not value:
        value = str(uuid7())
        request.state.correlation_id = value
    return str(value)


@router.post(
    "/product-concepts/{concept_id}/evaluations",
    status_code=201,
)
def evaluate(
    concept_id: uuid.UUID,
    request: Request,
    body: EvaluateRequest | None = None,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return evaluate_concept(
            session,
            tenant,
            concept_id,
            model_id=body.model_id if body is not None else None,
        )
    except ConceptNotFound:
        return _not_found(request, "Product concept not found.")
    except ScoringModelNotFound:
        return _not_found(request, "Scoring model not found.")
    except EvaluationValidationError as exc:
        return _validation(request, str(exc))


@router.get("/product-concepts/{concept_id}/evaluations/latest")
def latest(
    concept_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        result = get_latest_evaluation(session, tenant, concept_id)
    except EvaluationNotFound:
        return _not_found(request, "Evaluation not found.")
    if result is None:
        return _not_found(request, "Evaluation not found.")
    return result


@router.get("/evaluations/{evaluation_id}")
def detail(
    evaluation_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return get_evaluation(session, tenant, evaluation_id)
    except EvaluationNotFound:
        return _not_found(request, "Evaluation not found.")


@router.get("/evaluations/{evaluation_id}/explanation")
def explanation(
    evaluation_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return explain_evaluation(session, tenant, evaluation_id)
    except (EvaluationNotFound, ExplanationNotFound):
        return _not_found(request, "Evaluation not found.")


@router.post("/evaluations/batch", status_code=202)
def batch_evaluate(
    body: BatchEvaluateRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    correlation_id = _request_correlation_id(request)
    payload: dict[str, Any] = {
        "concept_ids": [str(item) for item in body.concept_ids],
        "requested_by": str(tenant.user_id),
        "requested_role": tenant.role,
    }
    if body.model_id is not None:
        payload["model_id"] = str(body.model_id)
    try:
        job = enqueue(
            "batch_evaluation",
            payload,
            idempotency_key=request.headers.get("Idempotency-Key"),
            correlation_id=correlation_id,
            session=session,
        )
    except InvalidJobType:
        return _validation(request, "Unknown job type.")
    except IdempotencyConflict:
        return error_response(
            request,
            status_code=409,
            code="conflict",
            message="Idempotency key is already used by another store.",
        )
    return {
        "id": str(job["id"]),
        "state": job["state"],
        "correlation_id": correlation_id,
    }


__all__ = ["router"]
