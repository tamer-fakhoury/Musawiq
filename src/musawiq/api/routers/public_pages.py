"""Public landing page route (unauthenticated, published pages only)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from musawiq.db.session import get_session_factory
from musawiq.middleware.errors import error_response
from musawiq.services.landing_pages import get_public_page
from musawiq.services.visitor_tracking import (
    VisitorTrackingError,
    create_session,
    first_party_script,
    hash_ip,
    ingest_event,
    set_consent,
)

router = APIRouter(tags=["public-pages"])


class TrackSessionRequest(BaseModel):
    consent_state: str = "unknown"
    tk: str | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None
    utm_term: str | None = None


class TrackEventRequest(BaseModel):
    session_id: str | None = None
    event_type: str
    event_id: str | None = None
    product_id: str | None = None
    adset_id: str | None = None
    ad_variation_id: str | None = None
    occurred_at: str | None = None
    url: str | None = None
    properties: dict[str, Any] | None = None


class ConsentRequest(BaseModel):
    session_id: str | None = None
    consent_state: str


def _ip_hash(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    client_ip = forwarded.split(",")[0].strip() if forwarded else None
    if not client_ip and request.client:
        client_ip = request.client.host
    return hash_ip(client_ip)


def _referrer(request: Request) -> str | None:
    return request.headers.get("Referer")


def _user_agent(request: Request) -> str | None:
    return request.headers.get("User-Agent")


def _tracking_error(request: Request, exc: VisitorTrackingError):
    return error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
    )


@router.get("/p/track.js")
def tracking_script():
    return Response(
        content=first_party_script(),
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/p/{slug}")
def read_public_page(slug: str, request: Request):
    session = get_session_factory()()
    try:
        page = get_public_page(session, slug)
    finally:
        session.close()
    if page is None:
        return error_response(
            request,
            status_code=404,
            code="page_unavailable",
            message="This page is unavailable.",
        )
    page["tracking"] = {
        "script_url": "/p/track.js",
        "session_url": f"/p/{slug}/track/session",
        "events_url": f"/p/{slug}/track/events",
        "consent_url": f"/p/{slug}/track/consent",
        "slug": slug,
    }
    return page


@router.post("/p/{slug}/track/session", status_code=201)
def track_session(slug: str, payload: TrackSessionRequest, request: Request):
    session = get_session_factory()()
    try:
        session.begin()
        result = create_session(
            session,
            slug,
            payload.model_dump(exclude_none=True),
            user_agent=_user_agent(request),
            ip_hash=_ip_hash(request),
            referrer=_referrer(request),
        )
        session.commit()
    except VisitorTrackingError as exc:
        session.rollback()
        return _tracking_error(request, exc)
    finally:
        session.close()
    response = JSONResponse(result, status_code=201)
    response.set_cookie(
        "msq_sid",
        result["session_id"],
        httponly=False,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/p/{slug}/track/events")
def track_event(slug: str, payload: TrackEventRequest, request: Request):
    data = payload.model_dump(exclude_none=True)
    if not data.get("session_id"):
        data["session_id"] = request.cookies.get("msq_sid")
    session = get_session_factory()()
    try:
        session.begin()
        result = ingest_event(
            session,
            slug,
            data,
            user_agent=_user_agent(request),
            ip_hash=_ip_hash(request),
            referrer=_referrer(request),
        )
        session.commit()
    except VisitorTrackingError as exc:
        session.rollback()
        return _tracking_error(request, exc)
    finally:
        session.close()
    return result


@router.post("/p/{slug}/track/consent")
def track_consent(slug: str, payload: ConsentRequest, request: Request):
    data = payload.model_dump(exclude_none=True)
    if not data.get("session_id"):
        data["session_id"] = request.cookies.get("msq_sid")
    session = get_session_factory()()
    try:
        session.begin()
        result = set_consent(session, slug, data)
        session.commit()
    except VisitorTrackingError as exc:
        session.rollback()
        return _tracking_error(request, exc)
    finally:
        session.close()
    return result


__all__ = ["router"]
