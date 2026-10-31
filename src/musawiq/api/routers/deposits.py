"""Deposit endpoints (manual confirmation and audit)."""

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
from musawiq.services.deposits import (
    DepositError,
    create_deposit,
    list_deposits,
    update_deposit,
)

router = APIRouter(tags=["deposits"])


class CreateDepositRequest(BaseModel):
    status: Literal["pending", "confirmed", "rejected"] = "pending"
    amount_minor: int | None = None
    currency: str | None = None
    method: Literal["manual", "payment_gateway"] = "manual"
    evidence_file_id: uuid.UUID | None = None
    external_payment_id: str | None = None


class UpdateDepositRequest(BaseModel):
    status: Literal["confirmed", "rejected"]
    amount_minor: int | None = None
    currency: str | None = None
    method: Literal["manual", "payment_gateway"] = "manual"
    evidence_file_id: uuid.UUID | None = None
    external_payment_id: str | None = None


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


def _deposit_error(request: Request, exc: DepositError):
    return error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
    )


@router.post("/orders/{order_id}/deposits", status_code=201)
def create(
    order_id: uuid.UUID,
    payload: CreateDepositRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return create_deposit(
            session, tenant, order_id, payload.model_dump(exclude_none=True)
        )
    except DepositError as exc:
        return _deposit_error(request, exc)


@router.get("/orders/{order_id}/deposits")
def list_for_order(
    order_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return list_deposits(session, tenant, order_id)
    except DepositError as exc:
        return _deposit_error(request, exc)


@router.patch("/deposits/{deposit_id}")
def update(
    deposit_id: uuid.UUID,
    payload: UpdateDepositRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return update_deposit(
            session, tenant, deposit_id, payload.model_dump(exclude_none=True)
        )
    except DepositError as exc:
        return _deposit_error(request, exc)


__all__ = ["router"]
