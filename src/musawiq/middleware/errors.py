"""Single error envelope and FastAPI exception handlers."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from musawiq.auth.errors import PermissionDenied
from musawiq.middleware.correlation import (
    CORRELATION_ID_HEADER,
    get_correlation_id,
    uuid7,
)

logger = logging.getLogger("musawiq.errors")

_HTTP_ERRORS: Mapping[int, tuple[str, str]] = {
    400: ("bad_request", "Request could not be processed."),
    401: ("unauthorized", "Authentication is required."),
    403: ("forbidden", "You do not have permission to perform this action."),
    404: ("not_found", "Resource not found."),
    405: ("method_not_allowed", "Method not allowed."),
    409: ("conflict", "The request conflicts with the current state."),
    422: ("validation_error", "Request validation failed."),
}


def _correlation_id(request: Request) -> str:
    value = getattr(request.state, "correlation_id", None) or get_correlation_id()
    if not value:
        value = str(uuid7())
        request.state.correlation_id = value
    return value


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    headers: Mapping[str, str] | None = None,
    fields: Mapping[str, str] | None = None,
) -> JSONResponse:
    correlation_id = _correlation_id(request)
    response_headers: dict[str, Any] = dict(headers or {})
    response_headers[CORRELATION_ID_HEADER] = correlation_id
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "correlation_id": correlation_id,
    }
    if fields:
        error["fields"] = dict(fields)
    return JSONResponse(
        status_code=status_code,
        content={"error": error},
        headers=response_headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return error_response(
        request,
        status_code=422,
        code="validation_error",
        message="Request validation failed.",
    )


async def permission_denied_handler(
    request: Request, exc: PermissionDenied
) -> JSONResponse:
    return error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    code, message = _HTTP_ERRORS.get(exc.status_code, ("http_error", "Request failed."))
    return error_response(
        request,
        status_code=exc.status_code,
        code=code,
        message=message,
        headers=exc.headers,
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        extra={
            "correlation_id": _correlation_id(request),
            "path": request.url.path,
            "status": 500,
            "error_type": type(exc).__name__,
        },
    )
    return error_response(
        request,
        status_code=500,
        code="internal_error",
        message="An unexpected error occurred.",
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(PermissionDenied, permission_denied_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


__all__ = [
    "error_response",
    "http_exception_handler",
    "install_error_handlers",
    "permission_denied_handler",
    "unhandled_exception_handler",
    "validation_exception_handler",
]
