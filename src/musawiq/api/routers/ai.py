"""AI status and generation endpoints."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from musawiq.ai.client import AIClient, UnavailableAIClient
from musawiq.ai.contract import AIResult
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService

router = APIRouter(prefix="/ai", tags=["ai"])

MANUAL_FALLBACK = (
    "Enter or edit the content manually; no AI-generated content is produced "
    "while the provider is unavailable."
)


class GenerateRequest(BaseModel):
    prompt_ref: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    input_snapshot_ref: dict[str, Any] = Field(default_factory=dict)


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        role = getattr(request.state, "role", None)
        if role is None:
            tenant = getattr(request.state, "tenant", None)
            role = getattr(tenant, "role", None)
        AuthorizationService().check(role, action)

    return dependency


def get_ai_client(request: Request) -> AIClient:
    return getattr(request.app.state, "ai_client", None) or UnavailableAIClient()


@router.get("/status")
def ai_status(
    client: AIClient = Depends(get_ai_client),
    _: None = Depends(_require_action(Action.READ)),
):
    available = bool(getattr(client, "available", True))
    degraded = bool(getattr(client, "degraded", not available))
    return {
        "available": available,
        "provider": getattr(client, "provider", "unknown"),
        "degraded": degraded,
        "manual_fallback": MANUAL_FALLBACK,
    }


@router.post("/generate")
def generate(
    body: GenerateRequest,
    client: AIClient = Depends(get_ai_client),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        result = client.generate(
            body.prompt_ref,
            model_version=body.model_version,
            prompt_version=body.prompt_version,
            input_snapshot_ref=body.input_snapshot_ref,
        )
    except Exception:
        result = AIResult(
            content=None,
            model_version=body.model_version,
            prompt_version=body.prompt_version,
            input_snapshot_ref=dict(body.input_snapshot_ref),
            generated_at=datetime.now(timezone.utc),
            provider=getattr(client, "provider", "unknown"),
            degraded=True,
            degraded_reason="The AI provider is unavailable.",
            retry_after_seconds=30,
            ai_generated=False,
        )

    return asdict(result)


__all__ = ["MANUAL_FALLBACK", "router"]
