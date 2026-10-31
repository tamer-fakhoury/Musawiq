"""Campaign, ad set, and ad variation endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from musawiq.ai.providers import get_provider
from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.middleware.errors import error_response
from musawiq.services.ad_variations import (
    AdVariationError,
    generate_variations,
)
from musawiq.services.campaigns import (
    CampaignError,
    CampaignNotFound,
    CampaignValidationError,
    create_adset,
    create_campaign,
    create_variation,
    get_campaign,
    list_campaigns,
    update_campaign,
    update_variation,
)
from musawiq.services.copy import (
    CopyNotFound,
    CopyProviderError,
    CopyUnavailable,
    CopyValidationError,
    suggest_copy,
)
from musawiq.services.preflight import PreflightError, validate as preflight
from musawiq.services.publication import (
    AdPlatformClient,
    PublicationError,
    publish_campaign,
)
from musawiq.services.tracking import (
    TrackingError,
    check_publication,
    generate_tracking_link,
    list_tracking_links,
)

router = APIRouter(tags=["campaigns"])


class CreateCampaignRequest(BaseModel):
    test_id: uuid.UUID | None = None
    provider: str
    name: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    budget_type: Literal["daily", "total"]
    budget_minor: int
    currency: str = Field(min_length=3, max_length=3)
    start_at: datetime
    end_at: datetime


class UpdateCampaignRequest(BaseModel):
    name: str | None = None
    budget_type: Literal["daily", "total"] | None = None
    budget_minor: int | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: Literal["draft", "active", "paused"] | None = None


class CreateAdSetRequest(BaseModel):
    name: str = Field(min_length=1)
    targeting: dict[str, Any]
    budget_type: Literal["daily", "total"] | None = None
    budget_minor: int | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    start_at: datetime | None = None
    end_at: datetime | None = None


class CreateVariationRequest(BaseModel):
    adset_id: uuid.UUID
    copy_text: str = Field(min_length=1)
    headline: str | None = None
    description: str | None = None
    post_id: uuid.UUID | None = None
    destination_url: str | None = None


class UpdateVariationRequest(BaseModel):
    copy_text: str | None = None
    headline: str | None = None
    description: str | None = None
    status: Literal["draft", "approved", "discarded"] | None = None


class SuggestCopyRequest(BaseModel):
    adset_id: uuid.UUID | None = None
    count: int = Field(default=3, ge=1, le=5)
    notes: str | None = None


class GenerateVariationsRequest(BaseModel):
    adset_id: uuid.UUID
    count: int = Field(default=3, ge=1, le=5)
    notes: str | None = None


class TrackingLinkRequest(BaseModel):
    adset_id: uuid.UUID | None = None
    ad_variation_id: uuid.UUID | None = None
    landing_page_id: uuid.UUID | None = None
    post_id: uuid.UUID | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None
    utm_term: str | None = None


class PublicationCheckRequest(BaseModel):
    adset_id: uuid.UUID | None = None
    ad_variation_id: uuid.UUID | None = None


class PublishCampaignRequest(BaseModel):
    confirm: bool = False
    approved_by: uuid.UUID | None = None


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


def _raise_for(exc: CampaignError) -> None:
    if isinstance(exc, CampaignNotFound):
        raise HTTPException(status_code=404, detail="Resource not found")
    if isinstance(exc, CampaignValidationError):
        raise HTTPException(status_code=422, detail=str(exc))
    raise exc


def _provider(request: Request):
    injected = getattr(request.app.state, "ai_provider", None)
    if injected is not None:
        return injected
    return get_provider(request.app.state.settings)


def _variation_error(request: Request, exc: AdVariationError):
    if exc.code == "not_found":
        status_code, code, message = 404, "not_found", "Resource not found."
    elif exc.code == "ai_unavailable":
        status_code, code, message = 503, "ai_unavailable", exc.message
    elif exc.code == "ai_invalid_output":
        status_code, code, message = 502, "ai_invalid_output", exc.message
    else:
        status_code, code, message = exc.status_code, exc.code, exc.message
    return error_response(
        request,
        status_code=status_code,
        code=code,
        message=message,
    )


def _platform_client(request: Request) -> AdPlatformClient | None:
    return getattr(request.app.state, "ad_platform_client", None)


def _publication_error(request: Request, exc: PublicationError):
    return error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
    )


def _tracking_error(request: Request, exc: TrackingError):
    return error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
    )


def _copy_error(request: Request, exc: Exception):
    if isinstance(exc, CopyNotFound):
        return error_response(
            request,
            status_code=404,
            code="not_found",
            message="Resource not found.",
        )
    if isinstance(exc, CopyUnavailable):
        return error_response(
            request,
            status_code=503,
            code="ai_unavailable",
            message=str(exc) or "The AI provider is unavailable.",
        )
    if isinstance(exc, CopyProviderError):
        return error_response(
            request,
            status_code=502,
            code="ai_invalid_output",
            message=str(exc) or "The AI provider returned invalid output.",
        )
    return error_response(
        request,
        status_code=422,
        code="validation_error",
        message=str(exc) or "Request validation failed.",
    )


@router.post("/campaigns", status_code=201)
def create(
    body: CreateCampaignRequest,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return create_campaign(session, tenant, body.model_dump())
    except CampaignError as exc:
        _raise_for(exc)


@router.get("/campaigns")
def list_all(
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    return list_campaigns(session, tenant)


@router.get("/campaigns/{campaign_id}")
def detail(
    campaign_id: uuid.UUID,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return get_campaign(session, tenant, campaign_id)
    except CampaignError as exc:
        _raise_for(exc)


@router.patch("/campaigns/{campaign_id}")
def patch(
    campaign_id: uuid.UUID,
    body: UpdateCampaignRequest,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return update_campaign(
            session,
            tenant,
            campaign_id,
            body.model_dump(exclude_unset=True),
        )
    except CampaignError as exc:
        _raise_for(exc)


@router.post("/campaigns/{campaign_id}/adsets", status_code=201)
def create_ad_set(
    campaign_id: uuid.UUID,
    body: CreateAdSetRequest,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return create_adset(session, tenant, campaign_id, body.model_dump())
    except CampaignError as exc:
        _raise_for(exc)


@router.post("/campaigns/{campaign_id}/variations", status_code=201)
def create_ad_variation(
    campaign_id: uuid.UUID,
    body: CreateVariationRequest,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return create_variation(
            session, tenant, campaign_id, body.model_dump()
        )
    except CampaignError as exc:
        _raise_for(exc)


@router.patch("/ad-variations/{variation_id}")
def patch_ad_variation(
    variation_id: uuid.UUID,
    body: UpdateVariationRequest,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return update_variation(
            session,
            tenant,
            variation_id,
            body.model_dump(exclude_unset=True),
        )
    except CampaignError as exc:
        _raise_for(exc)


@router.post("/campaigns/{campaign_id}/publish")
def publish_campaign_endpoint(
    campaign_id: uuid.UUID,
    request: Request,
    body: PublishCampaignRequest | None = None,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.SUBMIT_CAMPAIGN)),
):
    payload = body or PublishCampaignRequest()
    try:
        return publish_campaign(
            session,
            tenant,
            campaign_id,
            confirm=payload.confirm,
            approved_by=payload.approved_by,
            client=_platform_client(request),
        )
    except PublicationError as exc:
        return _publication_error(request, exc)


@router.get("/campaigns/{campaign_id}/preflight")
def campaign_preflight(
    campaign_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return preflight(session, tenant, campaign_id)
    except PreflightError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )


@router.post("/campaigns/{campaign_id}/tracking-links", status_code=201)
def create_tracking_link(
    campaign_id: uuid.UUID,
    request: Request,
    body: TrackingLinkRequest | None = None,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return generate_tracking_link(
            session, tenant, campaign_id, (body or TrackingLinkRequest()).model_dump()
        )
    except TrackingError as exc:
        return _tracking_error(request, exc)


@router.get("/campaigns/{campaign_id}/tracking-links")
def read_tracking_links(
    campaign_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return list_tracking_links(session, tenant, campaign_id)
    except TrackingError as exc:
        return _tracking_error(request, exc)


@router.post("/campaigns/{campaign_id}/publication-check")
def publication_check(
    campaign_id: uuid.UUID,
    request: Request,
    body: PublicationCheckRequest | None = None,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    payload = body.model_dump() if body else {}
    try:
        result = check_publication(session, tenant, campaign_id, payload)
    except TrackingError as exc:
        return _tracking_error(request, exc)
    if not result["valid"]:
        return error_response(
            request,
            status_code=422,
            code="tracking_invalid",
            message="; ".join(result["errors"]),
        )
    return result


@router.post("/campaigns/{campaign_id}/variations/generate", status_code=201)
def generate_ad_variations(
    campaign_id: uuid.UUID,
    request: Request,
    body: GenerateVariationsRequest,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return generate_variations(
            session,
            tenant,
            campaign_id,
            body.model_dump(),
            provider=_provider(request),
        )
    except AdVariationError as exc:
        return _variation_error(request, exc)


@router.post("/campaigns/{campaign_id}/variations/suggest")
def suggest_variations(
    campaign_id: uuid.UUID,
    request: Request,
    body: SuggestCopyRequest | None = None,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    payload = body or SuggestCopyRequest()
    try:
        return suggest_copy(
            session,
            tenant,
            campaign_id,
            adset_id=payload.adset_id,
            count=payload.count,
            notes=payload.notes,
            provider=_provider(request),
        )
    except (
        CopyNotFound,
        CopyUnavailable,
        CopyProviderError,
        CopyValidationError,
    ) as exc:
        return _copy_error(request, exc)


__all__ = ["router"]
