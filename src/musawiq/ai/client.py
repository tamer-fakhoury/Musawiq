"""AI client protocol and the safe unavailable fallback."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from musawiq.ai.contract import AIResult


class AIClient(Protocol):
    def generate(
        self,
        prompt_ref: str,
        *,
        model_version: str,
        prompt_version: str,
        input_snapshot_ref: dict[str, Any],
    ) -> AIResult:
        ...


class UnavailableAIClient:
    """Degrade safely without inventing content or evidence."""

    available = False
    provider = "unavailable"
    degraded = True

    def generate(
        self,
        prompt_ref: str,
        *,
        model_version: str,
        prompt_version: str,
        input_snapshot_ref: dict[str, Any],
    ) -> AIResult:
        return AIResult(
            content=None,
            model_version=model_version,
            prompt_version=prompt_version,
            input_snapshot_ref=dict(input_snapshot_ref),
            generated_at=datetime.now(timezone.utc),
            provider=self.provider,
            degraded=True,
            degraded_reason=(
                "The AI provider is unavailable. No content was generated."
            ),
            retry_after_seconds=30,
            ai_generated=False,
        )


__all__ = ["AIClient", "UnavailableAIClient"]
