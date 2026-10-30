"""Recommendation generation job handler."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text

from musawiq.db.session import get_session_factory
from musawiq.db.tenant import set_local_tenant
from musawiq.jobs.models import JobOutcome
from musawiq.services.recommendations import (
    mark_generation_failed,
    run_generation,
)

logger = logging.getLogger("musawiq.workers.recommendations")


def _store_owner(session, store_id) -> Any:
    return session.execute(
        text("SELECT owner_user_id FROM stores WHERE id = :id"),
        {"id": store_id},
    ).scalar_one()


def _progress(session, job_id, current: int, total: int) -> None:
    session.execute(
        text(
            """
            UPDATE async_jobs
            SET progress_current = :current, progress_total = :total
            WHERE id = :id
            """
        ),
        {"id": job_id, "current": current, "total": total},
    )


def _mark_failed(
    job: Mapping[str, Any], run_id: object, message: str
) -> None:
    session = get_session_factory()()
    try:
        session.begin()
        requested_by = (job.get("payload") or {}).get("requested_by") or (
            _store_owner(session, job["store_id"])
        )
        tenant = set_local_tenant(
            session,
            job["store_id"],
            requested_by,
            str((job.get("payload") or {}).get("requested_role") or "owner"),
        )
        mark_generation_failed(session, tenant, run_id, message)
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def run_recommendation_generation_job(
    job: Mapping[str, Any],
) -> JobOutcome:
    payload = job.get("payload") or {}
    run_id = payload.get("run_id")
    if not run_id:
        return JobOutcome(
            state="failed",
            error_code="invalid_payload",
            error_message="run_id is required",
        )

    session = get_session_factory()()
    try:
        session.begin()
        requested_by = payload.get("requested_by") or _store_owner(
            session, job["store_id"]
        )
        tenant = set_local_tenant(
            session,
            job["store_id"],
            requested_by,
            str(payload.get("requested_role") or "owner"),
        )
        _progress(session, job["id"], 0, 1)
        session.commit()
        tenant = set_local_tenant(
            session,
            job["store_id"],
            requested_by,
            str(payload.get("requested_role") or "owner"),
        )
        run = run_generation(session, tenant, run_id)
        _progress(session, job["id"], 1, 1)
        session.commit()
        return JobOutcome(
            state="succeeded",
            result={
                "run_id": run["id"],
                "returned_count": run["returned_count"],
            },
        )
    except Exception as exc:
        session.rollback()
        logger.exception(
            "recommendation_generation_job_failed",
            extra={
                "job_id": str(job.get("id")),
                "correlation_id": str(job.get("correlation_id")),
            },
        )
        safe_message = str(exc).strip()[:500] or "Recommendation generation failed."
        _mark_failed(job, run_id, safe_message)
        return JobOutcome(
            state="failed",
            error_code="generation_failed",
            error_message=safe_message,
        )
    finally:
        session.close()


__all__ = ["run_recommendation_generation_job"]
