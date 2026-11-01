"""Compatibility exports for :mod:`musawiq.auth.session`."""

from musawiq.auth.session import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    SessionError,
    create_session,
    has_valid_csrf,
    is_unsafe_cookie_request,
    new_csrf_token,
    parse_session,
    verify_session,
)

__all__ = [
    "CSRF_COOKIE",
    "CSRF_HEADER",
    "SESSION_COOKIE",
    "SESSION_MAX_AGE",
    "SessionError",
    "create_session",
    "has_valid_csrf",
    "is_unsafe_cookie_request",
    "new_csrf_token",
    "parse_session",
    "verify_session",
]
