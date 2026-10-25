"""Structured JSON logging and request logging middleware."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from musawiq.middleware.correlation import get_correlation_id

DEFAULT_SERVICE_NAME = "musawiq"
request_logger = logging.getLogger("musawiq.request")


class JsonFormatter(logging.Formatter):
    """Render one JSON object per log record."""

    def __init__(self, service: str = DEFAULT_SERVICE_NAME) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "service": getattr(record, "service", self.service),
            "level": record.levelname,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", None)
            or get_correlation_id(),
            "path": getattr(record, "path", None),
            "status": getattr(record, "status", None),
            "duration_ms": getattr(record, "duration_ms", None),
        }
        for key in ("store_id", "actor_user_id", "job_id", "error_type"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging(
    level: str | int = "INFO", service: str = DEFAULT_SERVICE_NAME
) -> None:
    """Install the JSON formatter on the root logger."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(service=service))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Emit one structured line per request without headers or bodies."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        extra: dict[str, Any] = {
            "correlation_id": getattr(request.state, "correlation_id", None)
            or get_correlation_id(),
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
        }
        for key in ("store_id", "actor_user_id"):
            value = getattr(request.state, key, None)
            if value is not None:
                extra[key] = str(value)

        request_logger.info("request", extra=extra)
        return response


__all__ = [
    "DEFAULT_SERVICE_NAME",
    "JsonFormatter",
    "RequestLoggingMiddleware",
    "configure_logging",
]
