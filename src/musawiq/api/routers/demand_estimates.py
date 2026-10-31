"""Demand estimate endpoints (FR-5.2.2)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.middleware.errors import error_response
from musawiq.services.demand_estimates import (
    DemandEstimateError,
    create_demand_estimate,
)

router = APIRouter(tags=["investment"])


class DemandEstimateRequest(BaseModel):
    profile_id: uuid.UUID | None = None
    profile: dict[str, Any] | None = None
    assumptions: dict[str, Any] | None = None


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


@router.post("/tests/{test_id}/demand-estimates", status_code=201)
def create_estimate(
    test_id: uuid.UUID,
    payload: DemandEstimateRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return create_demand_estimate(
            session, tenant, test_id, payload.model_dump(exclude_none=True)
        )
    except DemandEstimateError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )


__all__ = ["router"]
