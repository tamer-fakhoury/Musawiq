"""Health endpoint behaviour."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from musawiq.api.routers.health import database_is_ok


def test_health_ok_with_real_database(app) -> None:
    if not os.getenv("MUSAWIQ_TEST_DATABASE_URL"):
        app.dependency_overrides[database_is_ok] = lambda: True

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_degraded_does_not_leak_details(app) -> None:
    app.dependency_overrides[database_is_ok] = lambda: False

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "error"}
    body = response.text.lower()
    assert "postgresql" not in body
    assert "select 1" not in body
