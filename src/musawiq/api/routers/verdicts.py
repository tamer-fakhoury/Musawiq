"""Verdict input snapshot endpoints (FR-5.1.1)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.middleware.errors import error_response
from musawiq.services.verdicts import SnapshotError, compute_snapshot

router = APIRouter(tags=["verdicts"])


class SnapshotRequest(BaseModel):
    period_start: str
    period_end: str


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


@router.post("/tests/{test_id}/result-snapshots", status_code=201)
def create_snapshot(
    test_id: uuid.UUID,
    payload: SnapshotRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return compute_snapshot(
            session, tenant, test_id, payload.model_dump()
        )
    except SnapshotError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )


__all__ = ["router"]
