"""Health endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.session import get_session

HEARTBEAT_STALE_SECONDS = 90

router = APIRouter(tags=["health"])


def database_is_ok(session: Session = Depends(get_session)) -> bool:
    """Run the cheapest possible database probe.

    Exception details are deliberately discarded here so the endpoint cannot
    leak a DSN or driver message to a client.
    """
    try:
        session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@router.get("/health")
def health(database_ok: bool = Depends(database_is_ok)):
    if database_ok:
        return {"status": "ok", "database": "ok"}
    return JSONResponse(
        status_code=503,
        content={"status": "degraded", "database": "error"},
    )


@router.get("/health/workers")
def workers_health(session: Session = Depends(get_session)):
    rows = session.execute(
        text(
            """
            SELECT worker_name, status, processed_jobs, failed_jobs,
                   started_at, last_heartbeat_at,
                   (last_heartbeat_at < now() - make_interval(secs => :stale))
                       AS stale
            FROM worker_heartbeats
            ORDER BY last_heartbeat_at DESC
            """
        ),
        {"stale": HEARTBEAT_STALE_SECONDS},
    ).mappings().all()
    workers = [
        {
            "worker_name": row["worker_name"],
            "status": row["status"],
            "processed_jobs": row["processed_jobs"],
            "failed_jobs": row["failed_jobs"],
            "started_at": row["started_at"].isoformat(),
            "last_heartbeat_at": row["last_heartbeat_at"].isoformat(),
            "stale": row["stale"],
        }
        for row in rows
    ]
    return {"status": "ok", "workers": workers}


__all__ = ["HEARTBEAT_STALE_SECONDS", "database_is_ok", "health", "router"]
