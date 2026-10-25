"""Shared error envelope and correlation-ID contracts."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from musawiq.auth.errors import PermissionDenied
from musawiq.middleware.correlation import (
    CORRELATION_ID_HEADER,
    CorrelationIdMiddleware,
)
from musawiq.middleware.errors import install_error_handlers


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/echo-correlation")
    def echo_correlation(request: Request):
        return {"correlation_id": request.state.correlation_id}

    @app.get("/needs-int")
    def needs_int(value: int):
        return {"value": value}

    @app.get("/forbidden")
    def forbidden():
        raise PermissionDenied()

    @app.get("/boom")
    def boom():
        raise RuntimeError("postgresql://user:secret@127.0.0.1/musawiq")

    app.add_middleware(CorrelationIdMiddleware)

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_generates_uuid7_correlation_id(client) -> None:
    response = client.get("/echo-correlation")

    assert response.status_code == 200
    correlation_id = response.json()["correlation_id"]
    assert uuid.UUID(correlation_id).version == 7
    assert response.headers[CORRELATION_ID_HEADER] == correlation_id


def test_accepts_incoming_correlation_id(client) -> None:
    response = client.get(
        "/echo-correlation",
        headers={CORRELATION_ID_HEADER: "client-correlation-123"},
    )

    assert response.status_code == 200
    assert response.json()["correlation_id"] == "client-correlation-123"
    assert response.headers[CORRELATION_ID_HEADER] == "client-correlation-123"


def test_validation_error_uses_envelope(client) -> None:
    response = client.get("/needs-int", params={"value": "not-an-int"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["message"] == "Request validation failed."
    assert error["correlation_id"] == response.headers[CORRELATION_ID_HEADER]
    assert "traceback" not in response.text.lower()


def test_not_found_uses_envelope(client) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["message"] == "Resource not found."
    assert error["correlation_id"] == response.headers[CORRELATION_ID_HEADER]


def test_permission_denied_uses_envelope(client) -> None:
    response = client.get("/forbidden")

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "permission_denied"
    assert error["message"] == "You do not have permission to perform this action."
    assert error["correlation_id"] == response.headers[CORRELATION_ID_HEADER]


def test_unhandled_error_hides_internals(client) -> None:
    response = client.get("/boom")

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert error["message"] == "An unexpected error occurred."
    assert error["correlation_id"] == response.headers[CORRELATION_ID_HEADER]

    body = response.text.lower()
    assert "postgresql" not in body
    assert "secret" not in body
    assert "runtimeerror" not in body
    assert "traceback" not in body
