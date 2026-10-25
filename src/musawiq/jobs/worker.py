"""Job claiming and handler dispatch."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import get_tenant
from musawiq.jobs.handlers import JOB_HANDLERS
from musawiq.jobs.models import JobOutcome

TERMINAL_STATES = frozenset({"succeeded", "partial", "failed"})


def claim_next(session: Session) -> Mapping[str, Any] | None:
    """Claim one queued job in the active tenant, or return ``None``."""
    tenant = get_tenant(session)
    return session.execute(
        text(
            """
            WITH candidate AS (
                SELECT id
                FROM async_jobs
                WHERE state = 'queued'
                  AND store_id = :store_id
                ORDER BY created_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE async_jobs AS job
            SET state = 'running',
                started_at = now(),
                attempt_count = job.attempt_count + 1
            FROM candidate
            WHERE job.id = candidate.id
            RETURNING job.*
            """
        ),
        {"store_id": tenant.store_id},
    ).mappings().one_or_none()


def _safe_error_message(exc: Exception) -> str:
    message = str(exc).strip() or type(exc).__name__
    return message[:500]


def _finish(
    session: Session,
    job_id: Any,
    *,
    state: str,
    result: Any = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> Mapping[str, Any]:
    tenant = get_tenant(session)
    result_json = (
        json.dumps(result, default=str) if result is not None else None
    )
    return session.execute(
        text(
            """
            UPDATE async_jobs
            SET state = :state,
                result = CAST(:result AS jsonb),
                error_code = :error_code,
                error_message = :error_message,
                finished_at = now()
            WHERE id = :id
              AND store_id = :store_id
            RETURNING *
            """
        ),
        {
            "state": state,
            "result": result_json,
            "error_code": error_code,
            "error_message": error_message,
            "id": job_id,
            "store_id": tenant.store_id,
        },
    ).mappings().one()


def run_job(session: Session, job: Mapping[str, Any]) -> Mapping[str, Any]:
    """Dispatch a claimed job and persist its terminal state."""
    handler = JOB_HANDLERS.get(job["job_type"])
    if handler is None:
        return _finish(
            session,
            job["id"],
            state="failed",
            error_code="unknown_job_type",
            error_message=f"No handler registered for job type {job['job_type']!r}",
        )

    try:
        outcome = handler(job)
    except Exception as exc:
        return _finish(
            session,
            job["id"],
            state="failed",
            error_code="handler_error",
            error_message=_safe_error_message(exc),
        )

    if isinstance(outcome, JobOutcome):
        state = outcome.state if outcome.state in TERMINAL_STATES else "failed"
        if state == "failed":
            return _finish(
                session,
                job["id"],
                state="failed",
                error_code=outcome.error_code or "handler_failed",
                error_message=outcome.error_message or "Job handler failed",
            )
        return _finish(
            session,
            job["id"],
            state=state,
            result=outcome.result,
        )

    if outcome is None:
        return _finish(session, job["id"], state="succeeded")

    return _finish(session, job["id"], state="succeeded", result=outcome)


class JobWorker:
    """Convenience wrapper around the module-level worker functions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def claim_next(self) -> Mapping[str, Any] | None:
        return claim_next(self.session)

    def run_job(self, job: Mapping[str, Any]) -> Mapping[str, Any]:
        return run_job(self.session, job)


__all__ = ["JobWorker", "TERMINAL_STATES", "claim_next", "run_job"]
