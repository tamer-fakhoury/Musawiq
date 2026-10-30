"""Public landing page route (unauthenticated, published pages only)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from musawiq.db.session import get_session_factory
from musawiq.middleware.errors import error_response
from musawiq.services.landing_pages import get_public_page

router = APIRouter(tags=["public-pages"])


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
    return page


__all__ = ["router"]
