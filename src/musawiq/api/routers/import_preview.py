"""Import preview and error-report endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.errors import PermissionDenied
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.middleware.errors import error_response
from musawiq.services.import_preview import (
    ImportPreviewError,
    error_report,
    preview_batch,
)

router = APIRouter(prefix="/imports", tags=["imports"])


def _require_read(tenant: TenantContext = Depends(get_tenant)) -> None:
    try:
        AuthorizationService().check(tenant.role, Action.READ)
    except PermissionDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.get("/{batch_id}/preview")
def get_import_preview(
    batch_id: uuid.UUID,
    request: Request,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_read),
):
    try:
        return preview_batch(
            session,
            tenant,
            batch_id,
            limit=limit,
            offset=offset,
        )
    except ImportPreviewError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )


@router.get("/{batch_id}/error-report.csv")
def download_import_error_report(
    batch_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_read),
):
    try:
        content = error_report(session, tenant, batch_id)
    except ImportPreviewError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )

    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="import-{batch_id}-errors.csv"'
            )
        },
    )


__all__ = ["router"]
