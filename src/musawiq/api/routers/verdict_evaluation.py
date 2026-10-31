"""Verdict evaluation endpoints (FR-5.1.4)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.middleware.errors import error_response
from musawiq.services.verdict_evaluation import (
    VerdictError,
    evaluate_verdict,
    list_verdicts,
)
from musawiq.services.verdict_explanations import (
    ExplanationError,
    explain_verdict,
)

router = APIRouter(tags=["verdicts"])


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


def _error(request: Request, exc: VerdictError):
    return error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
    )


@router.post("/tests/{test_id}/verdicts", status_code=201)
def create_verdict(
    test_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return evaluate_verdict(session, tenant, test_id)
    except VerdictError as exc:
        return _error(request, exc)


@router.get("/verdicts/{verdict_id}/explanation")
def read_verdict_explanation(
    verdict_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return explain_verdict(session, tenant, verdict_id)
    except ExplanationError as exc:
        return _error(request, exc)


@router.get("/tests/{test_id}/verdicts")
def read_verdicts(
    test_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return list_verdicts(session, tenant, test_id)
    except VerdictError as exc:
        return _error(request, exc)


__all__ = ["router"]
