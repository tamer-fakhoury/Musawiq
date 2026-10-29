"""Customer feedback HTTP endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.middleware.errors import error_response
from musawiq.services.feedback import (
    FeedbackValidationError,
    list_feedback,
    submit_feedback,
    upload_feedback_file,
)

router = APIRouter(prefix="/feedback", tags=["feedback"])


class ManualFeedbackRequest(BaseModel):
    text: str
    language: str | None = None
    sentiment: str | None = None
    captured_at: str | None = None
    audience_profile_id: uuid.UUID | None = None


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


def _validation_response(
    request: Request, exc: FeedbackValidationError
):
    return error_response(
        request,
        status_code=422,
        code="validation_error",
        message="Feedback validation failed.",
        fields=exc.fields,
    )


@router.post("", status_code=201)
def create_manual(
    body: ManualFeedbackRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return submit_feedback(
            session,
            tenant,
            body.model_dump(exclude_none=True),
        )
    except FeedbackValidationError as exc:
        return _validation_response(request, exc)


@router.post("/file", status_code=201)
def upload_file(
    request: Request,
    file: UploadFile = File(...),
    audience_profile_id: uuid.UUID | None = Form(default=None),
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return upload_feedback_file(
            session,
            tenant,
            filename=file.filename or "",
            content_type=file.content_type or "",
            data=file.file.read(),
            audience_profile_id=audience_profile_id,
        )
    except FeedbackValidationError as exc:
        return _validation_response(request, exc)


@router.get("")
def list_all(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return list_feedback(
            session, tenant, limit=limit, offset=offset
        )
    except FeedbackValidationError as exc:
        return _validation_response(request, exc)


__all__ = ["router"]
