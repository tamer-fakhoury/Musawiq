"""Campaign AI analysis endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from musawiq.ai.analysis.service import (
    AnalysisNotFound,
    AnalysisRateLimited,
    AnalysisValidationError,
    create_analysis,
    get_analysis,
    list_analyses,
)
from musawiq.ai.providers import get_provider
from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.middleware.errors import error_response

router = APIRouter(tags=["analyses"])


class AnalysisRequest(BaseModel):
    window_start: datetime | None = None
    window_end: datetime | None = None
    parent_analysis_id: uuid.UUID | None = None


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


def _provider(request: Request):
    injected = getattr(request.app.state, "ai_provider", None)
    if injected is not None:
        return injected
    return get_provider(request.app.state.settings)


def _error(request: Request, exc: Exception):
    if isinstance(exc, AnalysisNotFound):
        return error_response(
            request,
            status_code=404,
            code="not_found",
            message="Resource not found.",
        )
    if isinstance(exc, AnalysisRateLimited):
        return error_response(
            request,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="rate_limited",
            message=str(exc),
        )
    return error_response(
        request,
        status_code=422,
        code="invalid_analysis",
        message=str(exc) or "The analysis result is invalid.",
    )


@router.post(
    "/campaigns/{campaign_id}/analyses",
    status_code=status.HTTP_201_CREATED,
)
def create(
    campaign_id: uuid.UUID,
    request: Request,
    body: AnalysisRequest | None = None,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return create_analysis(
            session,
            tenant,
            campaign_id,
            window_start=body.window_start if body else None,
            window_end=body.window_end if body else None,
            parent_analysis_id=(
                body.parent_analysis_id if body else None
            ),
            provider=_provider(request),
        )
    except (AnalysisNotFound, AnalysisRateLimited, AnalysisValidationError) as exc:
        return _error(request, exc)


@router.get("/campaigns/{campaign_id}/analyses")
def list_for_campaign(
    campaign_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return list_analyses(session, tenant, campaign_id)
    except AnalysisNotFound as exc:
        return _error(request, exc)


@router.get("/analyses/{analysis_id}")
def detail(
    analysis_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return get_analysis(session, tenant, analysis_id)
    except AnalysisNotFound as exc:
        return _error(request, exc)


__all__ = ["router"]
