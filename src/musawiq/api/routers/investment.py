"""Investment recalculation endpoints (FR-5.2.6)."""

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
from musawiq.services.investment import (
    InvestmentError,
    current,
    history,
    recalculate,
)
from musawiq.services.investment_profiles import (
    InvestmentProfileError,
    get_current_profile,
    list_profiles,
    upsert_profile,
)
from musawiq.services.investment_scenarios import ScenarioError, create_scenarios

router = APIRouter(tags=["investment"])


class RecalculateRequest(BaseModel):
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


@router.post("/tests/{test_id}/recommendations/recalculate", status_code=201)
def create_recalculation(
    test_id: uuid.UUID,
    payload: RecalculateRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return recalculate(
            session, tenant, test_id, payload.model_dump(exclude_none=True)
        )
    except InvestmentError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )


@router.get("/tests/{test_id}/recommendations")
def read_history(
    test_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return history(session, tenant, test_id)
    except InvestmentError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )


@router.get("/tests/{test_id}/recommendations/current")
def read_current_recommendation(
    test_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        result = current(session, tenant, test_id)
    except InvestmentError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )
    if result is None:
        return error_response(
            request,
            status_code=404,
            code="not_found",
            message="No investment recommendation exists.",
        )
    return result


@router.post("/tests/{test_id}/investment-profile", status_code=201)
def create_investment_profile(
    test_id: uuid.UUID,
    payload: dict[str, Any],
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return upsert_profile(session, tenant, test_id, payload)
    except InvestmentProfileError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            fields=exc.fields or None,
        )


@router.put("/tests/{test_id}/investment-profile")
def update_investment_profile(
    test_id: uuid.UUID,
    payload: dict[str, Any],
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return upsert_profile(session, tenant, test_id, payload)
    except InvestmentProfileError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            fields=exc.fields or None,
        )


@router.get("/tests/{test_id}/investment-profile")
def read_investment_profile(
    test_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return get_current_profile(session, tenant, test_id)
    except InvestmentProfileError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            fields=exc.fields or None,
        )


@router.get("/tests/{test_id}/investment-profiles")
def read_investment_profile_history(
    test_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return list_profiles(session, tenant, test_id)
    except InvestmentProfileError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            fields=exc.fields or None,
        )


@router.post("/tests/{test_id}/scenarios", status_code=201)
@router.post("/tests/{test_id}/quantity-scenarios", status_code=201)
def create_quantity_scenarios(
    test_id: uuid.UUID,
    request: Request,
    payload: dict[str, Any] | None = None,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return create_scenarios(session, tenant, test_id, payload)
    except ScenarioError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )


__all__ = ["router"]
