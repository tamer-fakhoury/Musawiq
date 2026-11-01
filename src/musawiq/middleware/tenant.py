"""Tenant resolution middleware.

P1-A2 uses a temporary development provider that reads identity from headers.
P1-A3 will replace the provider with the real authentication implementation; the
middleware and downstream dependencies do not change.

Protected request contract:
    X-Store-Id:  UUID of the active store
    X-User-Id:   UUID of the acting user
    X-User-Role: optional; owner | manager | analyst (default: analyst)

``/health`` and the documentation routes are public and bypass tenant
resolution. Every other route requires a valid tenant context.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from musawiq.auth.sessions import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE as SESSION_COOKIE_NAME,
    SessionError,
    parse_session,
)
from musawiq.db.session import get_session_factory
from musawiq.db.tenant import ROLES, TenantContext

PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/health/workers",
        "/openapi.json",
        "/auth/signup",
        "/auth/login",
        "/auth/verify",
        "/auth/verify/resend",
        "/auth/logout",
        "/auth/password/forgot",
        "/auth/password/reset",
    }
)
PUBLIC_PREFIXES = ("/docs", "/redoc", "/p/", "/r/")
CORRELATION_ID_HEADER = "X-Correlation-ID"


class TenantResolutionError(RuntimeError):
    """Raised when a request cannot be resolved to a valid tenant."""


class TenantProvider(Protocol):
    """Resolve request identity into a tenant context.

    P1-A3 replaces the development header provider with an implementation backed
    by the authenticated session.
    """

    def resolve(self, request: Request) -> TenantContext:
        ...


class DevHeaderTenantProvider:
    """Temporary development provider reading identity headers.

    When ``default_store_id`` and ``default_user_id`` are configured, requests
    without tenant headers fall back to that demo identity. This keeps browser
    navigation (for example Swagger UI) usable during local development. The
    application factory refuses this provider in production, so the fallback
    cannot be reached there.
    """

    def __init__(
        self,
        default_store_id: str | None = None,
        default_user_id: str | None = None,
        default_role: str | None = None,
    ) -> None:
        self.default_store_id = default_store_id
        self.default_user_id = default_user_id
        self.default_role = default_role

    def resolve(self, request: Request) -> TenantContext:
        store_header = request.headers.get("X-Store-Id") or self.default_store_id
        user_header = request.headers.get("X-User-Id") or self.default_user_id
        if not store_header or not user_header:
            raise TenantResolutionError(
                "X-Store-Id and X-User-Id headers are required"
            )

        try:
            store_id = uuid.UUID(store_header.strip())
            user_id = uuid.UUID(user_header.strip())
        except (ValueError, AttributeError) as exc:
            raise TenantResolutionError(
                "X-Store-Id and X-User-Id must be valid UUIDs"
            ) from exc

        role = (
            request.headers.get("X-User-Role")
            or self.default_role
            or "analyst"
        ).strip().lower()
        if role not in ROLES:
            raise TenantResolutionError(
                "X-User-Role must be one of owner, manager, analyst"
            )

        return TenantContext(store_id=store_id, user_id=user_id, role=role)


class SessionTenantProvider:
    """Resolve identity from the signed session cookie against the database.

    ``allow_header_fallback`` exists only for local development test suites;
    when disabled (production), requests without a valid session cookie are
    rejected with 401.
    """

    def __init__(self, *, allow_header_fallback: bool = False) -> None:
        self.allow_header_fallback = allow_header_fallback
        self._headers = DevHeaderTenantProvider()

    def _from_cookie(self, request: Request) -> TenantContext:
        try:
            payload = parse_session(request.cookies.get(SESSION_COOKIE_NAME))
        except SessionError as exc:
            raise TenantResolutionError("Authentication required.") from exc
        user_id = uuid.UUID(str(payload["user_id"]))
        session = get_session_factory()()
        try:
            session.begin()
            session.execute(
                text("SELECT set_config('app.auth_lookup', 'true', true)")
            )
            user = session.execute(
                text(
                    "SELECT id, role, status, email_verified_at, "
                    "password_changed_at FROM users "
                    "WHERE id = :id AND deleted_at IS NULL"
                ),
                {"id": user_id},
            ).mappings().one_or_none()
            if (
                user is None
                or user["status"] != "active"
                or user["email_verified_at"] is None
            ):
                raise TenantResolutionError("Authentication required.")
            changed_at = user["password_changed_at"]
            expected = changed_at.isoformat() if changed_at is not None else None
            if payload.get("pch") != expected:
                raise TenantResolutionError("Authentication required.")
            store = session.execute(
                text(
                    "SELECT id FROM stores WHERE owner_user_id = :user_id "
                    "AND deleted_at IS NULL ORDER BY created_at LIMIT 1"
                ),
                {"user_id": user_id},
            ).scalar_one_or_none()
            if store is None:
                raise TenantResolutionError("No store is available for this user.")
            return TenantContext(
                store_id=store,
                user_id=user["id"],
                role=user["role"],
            )
        finally:
            session.close()

    def resolve(self, request: Request) -> TenantContext:
        if SESSION_COOKIE_NAME in request.cookies:
            return self._from_cookie(request)
        if self.allow_header_fallback and (
            request.headers.get("X-Store-Id")
            or request.headers.get("X-User-Id")
        ):
            return self._headers.resolve(request)
        raise TenantResolutionError("Authentication required.")



DevSessionTenantProvider = SessionTenantProvider


def error_envelope(
    code: str, message: str, correlation_id: str
) -> dict[str, object]:
    """Shared user-facing error envelope.

    P1-A1b owns the final error middleware; this helper keeps the tenant
    middleware's 401 response in the same shape until that module lands.
    """
    return {
        "error": {
            "code": code,
            "message": message,
            "correlation_id": correlation_id,
        }
    }


def get_correlation_id(request: Request) -> str:
    """Return the request correlation id, creating one when absent."""
    existing = getattr(request.state, "correlation_id", None)
    if existing:
        return str(existing)

    header = request.headers.get(CORRELATION_ID_HEADER, "").strip()
    if header:
        try:
            value = str(uuid.UUID(header))
        except ValueError:
            value = str(uuid.uuid4())
    else:
        value = str(uuid.uuid4())

    request.state.correlation_id = value
    return value


class TenantMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, provider: TenantProvider) -> None:
        super().__init__(app)
        self.provider = provider

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        if request.url.path in PUBLIC_PATHS or request.url.path.startswith(
            PUBLIC_PREFIXES
        ):
            return await call_next(request)

        try:
            cookie_session = SESSION_COOKIE_NAME in request.cookies
            if (
                request.method in {"POST", "PUT", "PATCH", "DELETE"}
                and cookie_session
            ):
                import hmac as _hmac

                csrf_cookie = request.cookies.get(CSRF_COOKIE) or ""
                csrf_header = request.headers.get(CSRF_HEADER) or ""
                valid_csrf = bool(csrf_cookie) and _hmac.compare_digest(
                    csrf_cookie, csrf_header
                )
            else:
                valid_csrf = True
            if not valid_csrf:
                correlation_id = get_correlation_id(request)
                return JSONResponse(
                    status_code=403,
                    content=error_envelope(
                        "csrf_invalid",
                        "A valid CSRF token is required.",
                        correlation_id,
                    ),
                    headers={CORRELATION_ID_HEADER: correlation_id},
                )
            tenant = self.provider.resolve(request)
        except TenantResolutionError as exc:
            correlation_id = get_correlation_id(request)
            return JSONResponse(
                status_code=401,
                content=error_envelope(
                    "unauthorized",
                    str(exc),
                    correlation_id,
                ),
                headers={CORRELATION_ID_HEADER: correlation_id},
            )

        request.state.tenant = tenant
        get_correlation_id(request)
        return await call_next(request)
