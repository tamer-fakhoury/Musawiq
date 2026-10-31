"""Campaign signal ingestion endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from musawiq.api.deps import get_owned_or_404, get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.repositories.base import TenantScopedRepository
from musawiq.services.signals import (
    SignalValidationError,
    list_signals,
    write_signals,
)

router = APIRouter(tags=["signals"])


class SignalRow(BaseModel):
    adset_id: uuid.UUID | None = None
    ad_variation_id: uuid.UUID | None = None
    impressions: int = Field(ge=0)
    reach: int = Field(ge=0)
    clicks: int = Field(ge=0)
    spend_minor: int = Field(ge=0)
    conversions: int | None = Field(default=None, ge=0)
    engagement: int | None = Field(default=None, ge=0)


class SignalWindowRequest(BaseModel):
    period_start: datetime
    period_end: datetime
    provider: str = Field(min_length=1)
    rows: list[SignalRow]


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


def _campaign(
    campaign_id: uuid.UUID,
    request: Request,
    session: Session,
    tenant: TenantContext,
):
    repository = TenantScopedRepository(session, "campaigns")
    return get_owned_or_404(
        repository,
        campaign_id,
        target_type="campaign",
        tenant=tenant,
        request=request,
    )


@router.post("/campaigns/{campaign_id}/signals")
def ingest_signals(
    campaign_id: uuid.UUID,
    body: SignalWindowRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    campaign = _campaign(campaign_id, request, session, tenant)
    try:
        return write_signals(
            session, tenant, campaign, body.model_dump()
        )
    except SignalValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/campaigns/{campaign_id}/signals")
def list_campaign_signals(
    campaign_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    campaign = _campaign(campaign_id, request, session, tenant)
    return list_signals(session, tenant, campaign)


__all__ = ["router"]

from musawiq.api.routers.deposits import router as deposits_router

router.include_router(deposits_router)
from musawiq.api.routers.verdicts import router as verdicts_router

router.include_router(verdicts_router)
from musawiq.api.routers.decision_rules import router as decision_rules_router

router.include_router(decision_rules_router)
from musawiq.api.routers.verdict_evaluation import router as verdict_evaluation_router

router.include_router(verdict_evaluation_router)
