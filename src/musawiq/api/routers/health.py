"""Health endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.session import get_session

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
