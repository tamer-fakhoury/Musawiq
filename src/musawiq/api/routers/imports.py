"""Import upload, template, and batch history endpoints."""

from __future__ import annotations

import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import Response
from sqlalchemy.orm import Session

from musawiq.api.deps import get_owned_or_404, get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.imports.templates import template_bytes
from musawiq.middleware.errors import error_response
from musawiq.repositories.base import TenantScopedRepository
from musawiq.services.import_validation import (
    ImportValidationError,
    validate_import_batch,
)
from musawiq.services.imports import (
    MAX_UPLOAD_BYTES,
    ImportUploadError,
    batch_summary,
    create_import_batch,
    list_import_batches,
)

router = APIRouter(prefix="/imports", tags=["imports"])


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


@router.get("/template.csv")
def download_template():
    return Response(
        content=template_bytes(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="sales-template.csv"'
        },
    )


@router.post("", status_code=201)
def upload_import(
    request: Request,
    file: UploadFile = File(...),
    strict_mode: bool = Form(True),
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        return error_response(
            request,
            status_code=400,
            code="file_too_large",
            message="CSV files must be 20 MB or smaller.",
        )

    data = file.file.read()
    try:
        return create_import_batch(
            session,
            tenant,
            filename=file.filename or "",
            content_type=file.content_type or "",
            data=data,
            strict_mode=strict_mode,
        )
    except ImportUploadError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )


@router.get("")
def list_imports(
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    return list_import_batches(session, tenant)


@router.post("/{batch_id}/validate")
def validate_import(
    batch_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    repository = TenantScopedRepository(session, "import_batches")
    try:
        batch = get_owned_or_404(
            repository,
            batch_id,
            target_type="import_batch",
            tenant=tenant,
            request=request,
        )
    except HTTPException:
        return error_response(
            request,
            status_code=404,
            code="not_found",
            message="Resource not found.",
        )

    try:
        return validate_import_batch(session, tenant, batch)
    except ImportValidationError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )


@router.get("/{batch_id}")
def get_import(
    batch_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    repository = TenantScopedRepository(session, "import_batches")
    try:
        row = get_owned_or_404(
            repository,
            batch_id,
            target_type="import_batch",
            tenant=tenant,
            request=request,
        )
    except HTTPException:
        return error_response(
            request,
            status_code=404,
            code="not_found",
            message="Resource not found.",
        )
    return batch_summary(row)


__all__ = ["router"]
