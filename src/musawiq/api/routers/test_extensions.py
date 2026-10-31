"""Test extension endpoints (FR-5.1.7)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.middleware.errors import error_response
from musawiq.services.test_extensions import (
    ExtensionError,
    extend_test,
    list_extensions,
)

router = APIRouter(tags=["test-extensions"])


class ExtendTestRequest(BaseModel):
    new_end_at: str
    added_budget_minor: int
    reason: str | None = None
    approved_by: uuid.UUID | None = None
    recompute_policy: Literal["combined", "new_window"] = "combined"


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


def _error(request: Request, exc: ExtensionError):
    return error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
    )


@router.post("/tests/{test_id}/extensions", status_code=201)
def create_extension(
    test_id: uuid.UUID,
    payload: ExtendTestRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.EXTEND_TEST)),
):
    try:
        return extend_test(
            session, tenant, test_id, payload.model_dump(exclude_none=True)
        )
    except ExtensionError as exc:
        return _error(request, exc)


@router.get("/tests/{test_id}/extensions")
def read_extensions(
    test_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return list_extensions(session, tenant, test_id)
    except ExtensionError as exc:
        return _error(request, exc)


__all__ = ["router"]
