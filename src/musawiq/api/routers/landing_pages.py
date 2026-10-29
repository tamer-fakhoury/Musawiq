"""Landing page draft endpoints: product input, images, autosave."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.middleware.errors import error_response
from musawiq.services.landing_pages import (
    LandingPageError,
    create_draft,
    get_landing_page,
    save_draft,
    upload_product_image,
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
