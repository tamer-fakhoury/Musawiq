"""Recommendation generation and idea library HTTP endpoints."""

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
from musawiq.jobs.queue import enqueue
from musawiq.middleware.correlation import get_correlation_id, uuid7
from musawiq.middleware.errors import error_response
from musawiq.services.recommendations import (
    RecommendationNotFound,
    RecommendationValidationError,
    create_generation_run,
    dismiss_idea,
    get_generation_run,
    get_idea,
    get_ideas,
    list_generation_runs,
    restore_idea,
    save_idea,
)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


class GenerateRecommendationsRequest(BaseModel):
    count: int = Field(default=3, ge=1, le=10)


class DismissIdeaRequest(BaseModel):
    reason: str | None = None


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


def _correlation_id(request: Request) -> str:
    value = getattr(request.state, "correlation_id", None)
    if not value:
        value = get_correlation_id()
    if not value:
        value = str(uuid7())
        request.state.correlation_id = value
    return str(value)


def _validation(request: Request, message: str):
    return error_response(
        request,
        status_code=422,
        code="validation_error",
        message=message,
    )


def _not_found(request: Request):
    return error_response(
        request,
        status_code=404,
        code="not_found",
        message="Generation run not found.",
    )


@router.post("/generate", status_code=202)
def generate(
    body: GenerateRecommendationsRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        run = create_generation_run(session, tenant, body.count)
    except RecommendationValidationError as exc:
        return _validation(request, str(exc))
    correlation_id = _correlation_id(request)
    job = enqueue(
        "recommendation_generation",
        {
            "run_id": run["id"],
            "requested_by": str(tenant.user_id),
            "requested_role": tenant.role,
        },
        correlation_id=correlation_id,
        session=session,
    )
    return {
        "run_id": run["id"],
        "job_id": str(job["id"]),
        "status": run["status"],
        "correlation_id": correlation_id,
    }


@router.get("/runs")
def runs(
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    return list_generation_runs(session, tenant)


@router.get("/runs/{run_id}")
def run_detail(
    run_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return get_generation_run(session, tenant, run_id)
    except RecommendationNotFound:
        return _not_found(request)


@router.get("/ideas")
def ideas(
    request: Request,
    state: str | None = None,
    category_id: uuid.UUID | None = None,
    niche_id: uuid.UUID | None = None,
    generation_run_id: uuid.UUID | None = None,
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return get_ideas(
            session,
            tenant,
            state=state,
            category_id=category_id,
            niche_id=niche_id,
            generation_run_id=generation_run_id,
            limit=limit,
            offset=offset,
        )
    except RecommendationValidationError as exc:
        return _validation(request, str(exc))


@router.get("/ideas/{idea_id}")
def idea_detail(
    idea_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return get_idea(session, tenant, idea_id)
    except RecommendationNotFound:
        return _not_found(request)


@router.post("/ideas/{idea_id}/save")
def save(
    idea_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return save_idea(
            session,
            tenant,
            idea_id,
            correlation_id=_correlation_id(request),
        )
    except RecommendationNotFound:
        return _not_found(request)
    except RecommendationValidationError as exc:
        return _validation(request, str(exc))


@router.post("/ideas/{idea_id}/dismiss")
def dismiss(
    idea_id: uuid.UUID,
    request: Request,
    body: DismissIdeaRequest | None = None,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return dismiss_idea(
            session,
            tenant,
            idea_id,
            body.reason if body is not None else None,
            correlation_id=_correlation_id(request),
        )
    except RecommendationNotFound:
        return _not_found(request)
    except RecommendationValidationError as exc:
        return _validation(request, str(exc))


@router.post("/ideas/{idea_id}/restore")
def restore(
    idea_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return restore_idea(
            session,
            tenant,
            idea_id,
            correlation_id=_correlation_id(request),
        )
    except RecommendationNotFound:
        return _not_found(request)
    except RecommendationValidationError as exc:
        return _validation(request, str(exc))


__all__ = ["router"]
