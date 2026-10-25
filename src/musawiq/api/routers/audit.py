"""Read-only audit-log query and export surface.

There is deliberately no write, update, or delete HTTP route. Audit rows are
appended by trusted application services through ``AuditService.record``.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.errors import PermissionDenied
from musawiq.auth.permissions import Action, is_allowed
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.middleware.tenant import error_envelope, get_correlation_id
from musawiq.services.audit import AuditFilters, AuditService

router = APIRouter(prefix="/audit-logs", tags=["audit"])

CSV_COLUMNS = (
    "id",
    "created_at",
    "store_id",
    "actor_user_id",
    "actor_type",
    "action",
    "target_type",
    "target_id",
    "before",
    "after",
    "metadata",
    "correlation_id",
)


class AuditLogOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    store_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    actor_type: str
    action: str
    target_type: str
    target_id: uuid.UUID | None
    before: Any | None = None
    after: Any | None = None
    metadata: Any | None = None
    correlation_id: uuid.UUID | None


class AuditLogPage(BaseModel):
    items: list[AuditLogOut]
    total: int
    limit: int
    offset: int


def _deny(request: Request, message: str = "Permission denied") -> None:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=error_envelope(
            "forbidden",
            message,
            get_correlation_id(request),
        ),
    )


def _require_action(
    request: Request,
    tenant: TenantContext,
    action: Action,
) -> None:
    """Enforce one permission action.

    Uses P1-A3's ``AuthorizationService``. The service is resolved from
    ``app.state.authorization_service`` when a deployment installs one;
    otherwise the default service constructed from the permission matrix is
    used. ``PermissionDenied`` is converted to the shared error envelope.
    """
    service = getattr(request.app.state, "authorization_service", None)
    if service is None:
        service = AuthorizationService()

    check = getattr(service, "check", None)
    if check is not None:
        try:
            check(tenant.role, action)
        except PermissionDenied as exc:
            _deny(request, str(exc) or "Permission denied")
        return

    require = getattr(service, "require", None)
    if require is not None:
        try:
            allowed = require(tenant, action)
        except HTTPException:
            raise
        except PermissionDenied as exc:
            _deny(request, str(exc) or "Permission denied")
        except PermissionError as exc:
            _deny(request, str(exc) or "Permission denied")
        if allowed is False:
            _deny(request)
        return

    if not is_allowed(tenant.role, action):
        _deny(request)


def _filters(
    *,
    date_from: datetime | None,
    date_to: datetime | None,
    actor_user_id: uuid.UUID | None,
    target_type: str | None,
    target_id: uuid.UUID | None,
    action: str | None,
) -> AuditFilters:
    try:
        return AuditFilters(
            date_from=date_from,
            date_to=date_to,
            actor_user_id=actor_user_id,
            target_type=target_type,
            target_id=target_id,
            action=action,
        ).normalized()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _render_csv(rows: tuple[Any, ...]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow([_csv_value(row[column]) for column in CSV_COLUMNS])
    return buffer.getvalue()


@router.get("", response_model=AuditLogPage)
def list_audit_logs(
    request: Request,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    actor_user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    action: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(get_tenant),
    session: Session = Depends(get_session),
) -> AuditLogPage:
    _require_action(request, tenant, Action.READ)
    filters = _filters(
        date_from=date_from,
        date_to=date_to,
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_id=target_id,
        action=action,
    )
    try:
        page = AuditService.from_request(request, session).list_logs(
            filters,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return AuditLogPage(
        items=[AuditLogOut.model_validate(dict(row)) for row in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/export.csv")
def export_audit_logs(
    request: Request,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    actor_user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    action: str | None = None,
    tenant: TenantContext = Depends(get_tenant),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    # Owner-only proxy: until a dedicated export action exists, require the
    # owner-level approve_budget capability plus an explicit owner role check.
    _require_action(request, tenant, Action.APPROVE_BUDGET)
    if tenant.role != "owner":
        _deny(request, "Audit export is restricted to the store owner")

    filters = _filters(
        date_from=date_from,
        date_to=date_to,
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_id=target_id,
        action=action,
    )
    try:
        rows = AuditService.from_request(request, session).export_logs(filters)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return StreamingResponse(
        iter([_render_csv(rows)]),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="audit-logs.csv"'
        },
    )


__all__ = ["router"]
