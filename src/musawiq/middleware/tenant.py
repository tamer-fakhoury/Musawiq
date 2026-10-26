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
from starlette.middleware.base import BaseHTTPMiddleware

from musawiq.db.tenant import ROLES, TenantContext

PUBLIC_PATHS = frozenset({"/health", "/openapi.json"})
PUBLIC_PREFIXES = ("/docs", "/redoc")
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
    """Temporary development provider reading identity headers."""

    def resolve(self, request: Request) -> TenantContext:
        store_header = request.headers.get("X-Store-Id")
        user_header = request.headers.get("X-User-Id")
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

        role = (request.headers.get("X-User-Role") or "analyst").strip().lower()
        if role not in ROLES:
            raise TenantResolutionError(
                "X-User-Role must be one of owner, manager, analyst"
            )

        return TenantContext(store_id=store_id, user_id=user_id, role=role)


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
        if request.url.path in PUBLIC_PATHS or request.url.path.startswith(
            PUBLIC_PREFIXES
        ):
            return await call_next(request)

        try:
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
