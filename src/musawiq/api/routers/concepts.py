"""Product concept draft HTTP endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.middleware.errors import error_response
from musawiq.services.concepts import (
    CONCEPT_FIELDS,
    ConceptConflict,
    ConceptNotFound,
    ConceptValidationError,
    UploadedImage,
    create_concept,
    get_concept,
    update_concept,
    upload_product_image,
)

router = APIRouter(prefix="/product-concepts", tags=["concepts"])


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


def _validation_response(request: Request, exc: ConceptValidationError):
    return error_response(
        request,
        status_code=422,
        code="validation_error",
        message="Request validation failed.",
        fields=exc.fields,
    )


def _not_found_response(request: Request):
    return error_response(
        request,
        status_code=404,
        code="not_found",
        message="Product concept not found.",
    )


def _conflict_response(request: Request, exc: ConceptConflict):
    return error_response(
        request,
        status_code=409,
        code="conflict",
        message=str(exc),
    )


async def _read_payload(
    request: Request,
) -> tuple[dict[str, Any], UploadedImage | None]:
    content_type = (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    )

    if content_type == "application/json":
        try:
            body = await request.json()
        except (TypeError, ValueError) as exc:
            raise ConceptValidationError(
                {"body": "body must be valid JSON"}
            ) from exc
        if not isinstance(body, dict):
            raise ConceptValidationError(
                {"body": "body must be a JSON object"}
            )
        return body, None

    if content_type in {
        "multipart/form-data",
        "application/x-www-form-urlencoded",
    }:
        form = await request.form()
        payload = {
            field: form.get(field)
            for field in CONCEPT_FIELDS
            if field in form
        }
        upload = form.get("image") or form.get("file")
        image = None
        if upload is not None and hasattr(upload, "read"):
            image = UploadedImage(
                filename=getattr(upload, "filename", "") or "",
                content_type=getattr(upload, "content_type", "") or "",
                data=await upload.read(),
            )
        return payload, image

    raise ConceptValidationError(
        {
            "body": (
                "content type must be application/json or multipart/form-data"
            )
        }
    )


@router.post("", status_code=201)
async def create(
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        payload, image = await _read_payload(request)
        return create_concept(session, tenant, payload, image=image)
    except ConceptValidationError as exc:
        return _validation_response(request, exc)


@router.post("/images", status_code=201)
def upload_image(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return upload_product_image(
            session,
            tenant,
            filename=file.filename or "",
            content_type=file.content_type or "",
            data=file.file.read(),
        )
    except ConceptValidationError as exc:
        return _validation_response(request, exc)


@router.get("/{concept_id}")
def detail(
    concept_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return get_concept(session, tenant, concept_id)
    except ConceptNotFound:
        return _not_found_response(request)


@router.patch("/{concept_id}")
async def patch(
    concept_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        payload, image = await _read_payload(request)
        return update_concept(
            session,
            tenant,
            concept_id,
            payload,
            image=image,
        )
    except ConceptValidationError as exc:
        return _validation_response(request, exc)
    except ConceptNotFound:
        return _not_found_response(request)
    except ConceptConflict as exc:
        return _conflict_response(request, exc)


__all__ = ["router"]
