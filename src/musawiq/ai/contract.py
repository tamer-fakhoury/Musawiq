"""AI output contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class AIResult:
    """One AI generation result with provenance and degraded-mode metadata.

    ``input_snapshot_ref`` must contain ids and versions only (for example
    ``{"audience_profile_id": "...", "prompt_version": "v1"}``). Never put raw
    prompt text, customer data, or other PII in this field.
    """

    content: Any
    model_version: str
    prompt_version: str
    input_snapshot_ref: dict[str, Any]
    generated_at: datetime
    provider: str
    degraded: bool
    degraded_reason: str | None = None
    retry_after_seconds: int | None = None
    ai_generated: bool = True


__all__ = ["AIResult"]
