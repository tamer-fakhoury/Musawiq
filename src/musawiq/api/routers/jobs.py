"""Async job HTTP endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.jobs.queue import (
    IdempotencyConflict,
    InvalidJobType,
    enqueue,
)
from musawiq.middleware.correlation import get_correlation_id, uuid7

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        role = getattr(request.state, "role", None)
        if role is None:
            tenant = getattr(request.state, "tenant", None)
            role = getattr(tenant, "role", None)
        AuthorizationService().check(role, action)

    return dependency


def _request_correlation_id(request: Request) -> str:
    correlation_id = getattr(request.state, "correlation_id", None)
    if not correlation_id:
        correlation_id = get_correlation_id()
    if not correlation_id:
        correlation_id = str(uuid7())
        request.state.correlation_id = correlation_id
    return str(correlation_id)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _job_response(row) -> dict[str, Any]:
    last_updated = row["finished_at"] or row["started_at"] or row["created_at"]
    error = None
    if row["error_code"] is not None or row["error_message"] is not None:
        error = {
            "code": row["error_code"],
            "message": row["error_message"],
            "correlation_id": (
                str(row["correlation_id"])
                if row["correlation_id"] is not None
                else None
            ),
        }
    return {
        "id": str(row["id"]),
        "job_type": row["job_type"],
        "state": row["state"],
        "attempts": row["attempt_count"],
        "last_updated": _iso(last_updated),
        "error": error,
    }


@router.post("/{job_type}", status_code=202)
def create_job(
    job_type: str,
    request: Request,
    payload: dict[str, Any] | None = Body(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
    _: None = Depends(_require_action(Action.WRITE)),
):
    correlation_id = _request_correlation_id(request)
    try:
        job = enqueue(
            job_type,
            payload or {},
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            session=session,
        )
    except InvalidJobType:
        raise HTTPException(status_code=422, detail="Unknown job type")
    except IdempotencyConflict:
        raise HTTPException(
            status_code=409,
            detail="Idempotency key is already used by another store",
        )

    return {
        "id": str(job["id"]),
        "state": job["state"],
        "correlation_id": correlation_id,
    }


@router.get("/{job_id}")
def get_job(
    job_id: uuid.UUID,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    row = session.execute(
        text(
            """
            SELECT * FROM async_jobs
            WHERE id = :id AND store_id = :store_id
            """
        ),
        {"id": job_id, "store_id": tenant.store_id},
    ).mappings().one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return _job_response(row)


@router.post("/{job_id}/retry", status_code=202)
def retry_job(
    job_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    row = session.execute(
        text(
            """
            SELECT * FROM async_jobs
            WHERE id = :id AND store_id = :store_id
            FOR UPDATE
            """
        ),
        {"id": job_id, "store_id": tenant.store_id},
    ).mappings().one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if row["state"] != "failed":
        raise HTTPException(
            status_code=409,
            detail="Only failed jobs can be retried",
        )

    updated = session.execute(
        text(
            """
            UPDATE async_jobs
            SET state = 'queued',
                started_at = NULL,
                finished_at = NULL,
                error_code = NULL,
                error_message = NULL,
                result = NULL
            WHERE id = :id AND store_id = :store_id
            RETURNING *
            """
        ),
        {"id": job_id, "store_id": tenant.store_id},
    ).mappings().one()

    return {
        "id": str(updated["id"]),
        "state": updated["state"],
        "correlation_id": _request_correlation_id(request),
    }


__all__ = ["router"]
