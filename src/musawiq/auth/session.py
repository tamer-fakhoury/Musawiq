"""Stateless signed session and CSRF cookies (FR-0.6.3)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from typing import Any

from fastapi import Request

from musawiq.config import ConfigurationError, get_settings

SESSION_COOKIE = "msq_session"
CSRF_COOKIE = "msq_csrf"
CSRF_HEADER = "X-CSRF-Token"
SESSION_MAX_AGE = 7 * 24 * 60 * 60
SESSION_VERSION = 1


class SessionError(ValueError):
    """Raised when a session cookie cannot be trusted."""


def _secret() -> bytes:
    settings = get_settings()
    if settings.session_secret:
        return settings.session_secret.encode("utf-8")
    if settings.app_env != "development":
        raise ConfigurationError(
            "MUSAWIQ_SESSION_SECRET is required outside development"
        )
    return hashlib.sha256(
        f"musawiq-development-session:{settings.database_url}".encode("utf-8")
    ).digest()


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _sign(payload: bytes) -> str:
    return _b64(hmac.new(_secret(), payload, hashlib.sha256).digest())


def create_session(
    user_id: uuid.UUID | str,
    store_id: uuid.UUID | str | None,
) -> str:
    now = int(time.time())
    payload = {
        "schema_version": SESSION_VERSION,
        "uid": str(user_id),
        "sid": str(store_id) if store_id else None,
        "user_id": str(user_id),
        "store_id": str(store_id) if store_id else None,
        "iat": now,
        "exp": now + SESSION_MAX_AGE,
    }
    encoded = _b64(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    return f"{encoded}.{_sign(encoded.encode('ascii'))}"


def parse_session(value: str | None) -> dict[str, Any]:
    if not isinstance(value, str) or "." not in value:
        raise SessionError("invalid session")
    encoded, signature = value.rsplit(".", 1)
    expected = _sign(encoded.encode("ascii"))
    if not hmac.compare_digest(signature, expected):
        raise SessionError("invalid session signature")
    try:
        payload = json.loads(_unb64(encoded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SessionError("invalid session payload") from exc
    if payload.get("schema_version") != SESSION_VERSION:
        raise SessionError("unsupported session version")
    if int(payload.get("exp", 0)) <= int(time.time()):
        raise SessionError("session expired")
    return payload


def verify_session(value: str | None) -> dict[str, Any] | None:
    try:
        return parse_session(value)
    except SessionError:
        return None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def is_unsafe_cookie_request(request: Request) -> bool:
    return (
        SESSION_COOKIE in request.cookies
        and request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
    )


def has_valid_csrf(request: Request) -> bool:
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header:
        return False
    return hmac.compare_digest(cookie, header)


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
