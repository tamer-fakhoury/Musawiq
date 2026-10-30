"""Landing page draft endpoints: product input, images, autosave."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from musawiq.api.deps import get_session, get_tenant
from musawiq.ai.providers import get_provider
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.middleware.errors import error_response
from musawiq.services.landing_pages import (
    LandingPageError,
    create_draft,
    get_landing_page,
    preview as preview_page,
    publish as publish_page,
    save_draft,
    unpublish as unpublish_page,
    upload_product_image,
)
from musawiq.services.page_copy import (
    PageCopyError,
    generate_copy,
    update_copy,
)
from musawiq.services.page_generation import request_generation
from musawiq.services.order_channels import (
    OrderChannelError,
    configure as configure_order_channel,
    describe as describe_order_channel,
    verify as verify_order_channel,
)

router = APIRouter(prefix="/landing-pages", tags=["landing-pages"])


class OrderMethodInput(BaseModel):
    type: Literal["whatsapp", "cod"]
    whatsapp_number: str | None = None
    whatsapp_message_template: str | None = None
    cod_form_schema: dict[str, Any] | None = None


class DraftRequest(BaseModel):
    name: str
    description: str | None = None
    price_minor: int
    currency: str = Field(min_length=3, max_length=3)
    language: str = Field(min_length=2, max_length=8)
    target_market: str = Field(min_length=2, max_length=2)
    image_file_ids: list[uuid.UUID] = Field(default_factory=list)
    order_method: OrderMethodInput


class CreateDraftRequest(DraftRequest):
    product_concept_id: uuid.UUID
    template_id: uuid.UUID | None = None


class GenerateCopyRequest(BaseModel):
    force: bool = False


class UpdateCopyRequest(BaseModel):
    headline: str | None = None
    description: str | None = None
    cta_label: str | None = None
    body: str | None = None


class OrderChannelRequest(BaseModel):
    type: Literal["whatsapp", "cod"]
    whatsapp_number: str | None = None
    whatsapp_message_template: str | None = None
    cod_form_schema: dict[str, Any] | None = None


class PublishRequest(BaseModel):
    confirm: bool = False


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


def _error(request: Request, exc: LandingPageError):
    return error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
    )


def _copy_error(request: Request, exc: PageCopyError):
    return error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
    )


def _order_error(request: Request, exc: OrderChannelError):
    return error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
    )


def _provider(request: Request):
    injected = getattr(request.app.state, "ai_provider", None)
    if injected is not None:
        return injected
    return get_provider(request.app.state.settings)


@router.post("/images", status_code=201)
def upload_image(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    data = file.file.read()
    try:
        return upload_product_image(
            session,
            tenant,
            filename=file.filename or "",
            content_type=file.content_type or "",
            data=data,
        )
    except LandingPageError as exc:
        return _error(request, exc)


@router.post("/drafts", status_code=201)
def create(
    payload: CreateDraftRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return create_draft(session, tenant, payload.model_dump())
    except LandingPageError as exc:
        return _error(request, exc)


@router.put("/{page_id}/draft")
def autosave(
    page_id: uuid.UUID,
    payload: DraftRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return save_draft(session, tenant, page_id, payload.model_dump())
    except LandingPageError as exc:
        return _error(request, exc)


@router.get("/{page_id}/preview")
def preview(
    page_id: uuid.UUID,
    request: Request,
    version_id: uuid.UUID | None = None,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return preview_page(session, tenant, page_id, version_id)
    except LandingPageError as exc:
        return _error(request, exc)


@router.post("/{page_id}/publish")
def publish(
    page_id: uuid.UUID,
    payload: PublishRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    if not payload.confirm:
        return _error(
            request,
            LandingPageError(
                "confirmation_required",
                "Publishing requires explicit confirmation.",
            ),
        )
    try:
        return publish_page(session, tenant, page_id)
    except LandingPageError as exc:
        return _error(request, exc)


@router.post("/{page_id}/unpublish")
def unpublish(
    page_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return unpublish_page(session, tenant, page_id)
    except LandingPageError as exc:
        return _error(request, exc)


@router.get("/{page_id}/order-channel")
def read_order_channel(
    page_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return describe_order_channel(session, tenant, page_id)
    except OrderChannelError as exc:
        return _order_error(request, exc)


@router.put("/{page_id}/order-channel")
def save_order_channel(
    page_id: uuid.UUID,
    payload: OrderChannelRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return configure_order_channel(
            session, tenant, page_id, payload.model_dump()
        )
    except OrderChannelError as exc:
        return _order_error(request, exc)


@router.post("/{page_id}/order-channel/verify")
def check_order_channel(
    page_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return verify_order_channel(session, tenant, page_id)
    except OrderChannelError as exc:
        return _order_error(request, exc)


@router.post("/{page_id}/copy")
def create_copy(
    page_id: uuid.UUID,
    payload: GenerateCopyRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return generate_copy(
            session,
            tenant,
            page_id,
            force=payload.force,
            provider=_provider(request),
        )
    except PageCopyError as exc:
        return _copy_error(request, exc)


@router.put("/{page_id}/copy")
def edit_copy(
    page_id: uuid.UUID,
    payload: UpdateCopyRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return _copy_error(
            request,
            PageCopyError("invalid_copy", "At least one copy field is required."),
        )
    try:
        return update_copy(session, tenant, page_id, fields=fields)
    except PageCopyError as exc:
        return _copy_error(request, exc)


@router.post("/{page_id}/generate", status_code=202)
def generate(
    page_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        job = request_generation(session, tenant, page_id)
    except LandingPageError as exc:
        return _error(request, exc)
    return {
        "job_id": str(job["id"]),
        "state": job["state"],
    }


@router.get("/{page_id}")
def read(
    page_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return get_landing_page(session, tenant, page_id)
    except LandingPageError as exc:
        return _error(request, exc)


__all__ = ["router"]
