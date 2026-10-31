"""Decision rule set configuration endpoints (FR-5.1.3)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.middleware.errors import error_response
from musawiq.services.decision_rules import (
    DecisionRuleError,
    list_rule_sets,
    resolve_rule_set,
    upsert_rule_set,
)

router = APIRouter(tags=["decision-rules"])


class RuleSetRequest(BaseModel):
    category_id: uuid.UUID | None = None
    min_spend_minor: int | None = None
    min_clicks: int | None = None
    min_conversions: int | None = None
    min_confirmed_deposits: int | None = None
    min_conversion_rate: float | None = None
    max_cost_per_conversion_minor: int | None = None
    rules: dict[str, Any] = Field(default_factory=dict)


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


def _rule_error(request: Request, exc: DecisionRuleError):
    return error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
    )


@router.post("/decision-rule-sets", status_code=201)
def create_rule_set(
    payload: RuleSetRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return upsert_rule_set(
            session, tenant, payload.model_dump(exclude_unset=True)
        )
    except DecisionRuleError as exc:
        return _rule_error(request, exc)


@router.get("/decision-rule-sets")
def read_rule_sets(
    request: Request,
    category_id: uuid.UUID | None = Query(default=None),
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return list_rule_sets(session, tenant, category_id)
    except DecisionRuleError as exc:
        return _rule_error(request, exc)


@router.get("/decision-rule-sets/resolved")
def read_resolved_rule_set(
    request: Request,
    category_id: uuid.UUID | None = Query(default=None),
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        resolved = resolve_rule_set(session, tenant, category_id)
    except DecisionRuleError as exc:
        return _rule_error(request, exc)
    if resolved is None:
        return error_response(
            request,
            status_code=404,
            code="not_configured",
            message="No decision rule set is configured.",
        )
    return resolved


__all__ = ["router"]
