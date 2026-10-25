"""Structured JSON logging contracts."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from musawiq.logging import JsonFormatter, RequestLoggingMiddleware
from musawiq.middleware.correlation import CorrelationIdMiddleware


def test_json_formatter_has_required_fields() -> None:
    stream = io.StringIO()
    logger = logging.getLogger("musawiq.test.formatter")
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(service="test-service"))
    old_handlers = logger.handlers[:]
    old_propagate = logger.propagate
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    try:
        logger.info(
            "hello",
            extra={
                "correlation_id": "correlation-123",
                "path": "/widgets",
                "status": 201,
                "duration_ms": 12.5,
                "store_id": "store-1",
                "actor_user_id": "user-1",
            },
        )
    finally:
        logger.handlers = old_handlers
        logger.propagate = old_propagate
        handler.close()

    record = json.loads(stream.getvalue())
    assert record["service"] == "test-service"
    assert record["level"] == "INFO"
    assert record["message"] == "hello"
    assert record["correlation_id"] == "correlation-123"
    assert record["path"] == "/widgets"
    assert record["status"] == 201
    assert record["duration_ms"] == 12.5
    assert record["store_id"] == "store-1"
    assert record["actor_user_id"] == "user-1"


@pytest.fixture()
def logging_client() -> Iterator[tuple[TestClient, io.StringIO]]:
    stream = io.StringIO()
    logger = logging.getLogger("musawiq.request")
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(service="test-service"))
    old_handlers = logger.handlers[:]
    old_level = logger.level
    old_propagate = logger.propagate
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    app = FastAPI()

    @app.post("/echo")
    def echo():
        return {"ok": True}

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    try:
        with TestClient(app) as test_client:
            yield test_client, stream
    finally:
        logger.handlers = old_handlers
        logger.setLevel(old_level)
        logger.propagate = old_propagate
        handler.close()


def test_request_log_is_structured_and_redacted(logging_client) -> None:
    client, stream = logging_client

    response = client.post(
        "/echo",
        params={"token": "secret-query"},
        headers={
            "Authorization": "Bearer secret-token",
            "X-Correlation-ID": "log-correlation-1",
            "Content-Type": "application/json",
        },
        content='{"password":"secret-body"}',
    )

    assert response.status_code == 200
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])

    assert record["service"] == "test-service"
    assert record["level"] == "INFO"
    assert record["message"] == "request"
    assert record["correlation_id"] == "log-correlation-1"
    assert record["path"] == "/echo"
    assert record["status"] == 200
    assert isinstance(record["duration_ms"], (int, float))

    rendered = lines[0].lower()
    assert "secret-query" not in rendered
    assert "secret-token" not in rendered
    assert "secret-body" not in rendered
    assert "authorization" not in rendered
    assert "password" not in rendered
