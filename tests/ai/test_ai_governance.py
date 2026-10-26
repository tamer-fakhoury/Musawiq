"""AI governance and degraded-mode contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from musawiq.ai.client import UnavailableAIClient
from musawiq.ai.contract import AIResult
from musawiq.ai.policy import training_allowed
from musawiq.api.routers.ai import router as ai_router
from musawiq.middleware.correlation import CORRELATION_ID_HEADER, CorrelationIdMiddleware
from musawiq.middleware.errors import install_error_handlers

INPUT_REF = {
    "product_concept_id": "11111111-1111-1111-1111-111111111111",
    "audience_profile_version": "2",
}


class StubAIClient:
    available = True
    provider = "stub-provider"
    degraded = False

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate(
        self,
        prompt_ref: str,
        *,
        model_version: str,
        prompt_version: str,
        input_snapshot_ref: dict,
    ) -> AIResult:
        self.calls.append(
            {
                "prompt_ref": prompt_ref,
                "model_version": model_version,
                "prompt_version": prompt_version,
                "input_snapshot_ref": input_snapshot_ref,
            }
        )
        return AIResult(
            content={"copy": "Generated copy"},
            model_version=model_version,
            prompt_version=prompt_version,
            input_snapshot_ref=dict(input_snapshot_ref),
            generated_at=datetime.now(timezone.utc),
            provider=self.provider,
            degraded=False,
            ai_generated=True,
        )


class RoleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        role = request.headers.get("X-Test-Role", "owner")
        request.state.role = role
        request.state.tenant = SimpleNamespace(role=role)
        return await call_next(request)


@pytest.fixture()
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(ai_router)
    install_error_handlers(app)
    app.add_middleware(RoleMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.state.ai_client = UnavailableAIClient()
    return app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _generate_body() -> dict:
    return {
        "prompt_ref": "prompt-ref-123",
        "model_version": "model-v1",
        "prompt_version": "prompt-v1",
        "input_snapshot_ref": INPUT_REF,
    }


def test_available_result_carries_provenance(app, client) -> None:
    stub = StubAIClient()
    app.state.ai_client = stub

    response = client.post("/ai/generate", json=_generate_body())

    assert response.status_code == 200
    body = response.json()
    assert body["content"] == {"copy": "Generated copy"}
    assert body["model_version"] == "model-v1"
    assert body["prompt_version"] == "prompt-v1"
    assert body["input_snapshot_ref"] == INPUT_REF
    assert body["provider"] == "stub-provider"
    assert body["degraded"] is False
    assert body["ai_generated"] is True
    assert body["generated_at"]

    assert stub.calls == [
        {
            "prompt_ref": "prompt-ref-123",
            "model_version": "model-v1",
            "prompt_version": "prompt-v1",
            "input_snapshot_ref": INPUT_REF,
        }
    ]


def test_unavailable_client_degrades_without_content(client) -> None:
    response = client.post("/ai/generate", json=_generate_body())

    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] is True
    assert body["ai_generated"] is False
    assert body["content"] is None
    assert "unavailable" in body["degraded_reason"].lower()
    assert isinstance(body["retry_after_seconds"], int)
    assert body["retry_after_seconds"] > 0


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        ({}, False),
        ({"ai_training_opt_in": False}, False),
        ({"ai_training_opt_in": 1}, False),
        ({"ai_training_opt_in": "true"}, False),
        ({"ai_training_opt_in": True}, True),
    ],
)
def test_training_allowed_requires_explicit_boolean(settings, expected) -> None:
    assert training_allowed(settings) is expected


def test_status_reflects_unavailable_default(client) -> None:
    response = client.get("/ai/status")

    assert response.status_code == 200
    assert response.json() == {
        "available": False,
        "provider": "unavailable",
        "degraded": True,
        "manual_fallback": (
            "Enter or edit the content manually; no AI-generated content is "
            "produced while the provider is unavailable."
        ),
    }


def test_status_reflects_available_client(app, client) -> None:
    app.state.ai_client = StubAIClient()

    response = client.get("/ai/status")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["provider"] == "stub-provider"
    assert body["degraded"] is False
    assert body["manual_fallback"]


def test_status_allows_read_only_role(client) -> None:
    response = client.get("/ai/status", headers={"X-Test-Role": "analyst"})

    assert response.status_code == 200


def test_generate_requires_write_role(client) -> None:
    response = client.post(
        "/ai/generate",
        json=_generate_body(),
        headers={"X-Test-Role": "analyst"},
    )

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "permission_denied"
    assert error["correlation_id"] == response.headers[CORRELATION_ID_HEADER]
