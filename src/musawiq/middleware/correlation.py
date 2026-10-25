"""Correlation ID generation, request middleware, and context access."""

from __future__ import annotations

import os
import re
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

CORRELATION_ID_HEADER = "X-Correlation-ID"
_MAX_CORRELATION_ID_LENGTH = 128
_VALID_CORRELATION_ID = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,%d}$" % (_MAX_CORRELATION_ID_LENGTH - 1)
)

_correlation_id: ContextVar[str | None] = ContextVar(
    "correlation_id", default=None
)


def uuid7() -> uuid.UUID:
    """Generate an RFC 9562 UUIDv7."""
    timestamp_ms = time.time_ns() // 1_000_000
    value = bytearray(os.urandom(16))
    value[0:6] = timestamp_ms.to_bytes(6, "big")
    value[6] = (value[6] & 0x0F) | 0x70
    value[8] = (value[8] & 0x3F) | 0x80
    return uuid.UUID(bytes=bytes(value))


def normalize_correlation_id(value: str | None) -> str | None:
    """Return a safe correlation ID, or ``None`` when the value is unusable."""
    if value is None:
        return None
    candidate = value.strip()
    if not candidate or not _VALID_CORRELATION_ID.fullmatch(candidate):
        return None
    return candidate


def get_correlation_id() -> str | None:
    """Return the correlation ID for the current task."""
    return _correlation_id.get()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Accept or generate a correlation ID for every request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        correlation_id = normalize_correlation_id(
            request.headers.get(CORRELATION_ID_HEADER)
        )
        if correlation_id is None:
            correlation_id = str(uuid7())

        request.state.correlation_id = correlation_id
        token = _correlation_id.set(correlation_id)
        try:
            response = await call_next(request)
        finally:
            _correlation_id.reset(token)

        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response


__all__ = [
    "CORRELATION_ID_HEADER",
    "CorrelationIdMiddleware",
    "get_correlation_id",
    "normalize_correlation_id",
    "uuid7",
]
