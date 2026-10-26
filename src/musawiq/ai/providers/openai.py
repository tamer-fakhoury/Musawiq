"""OpenAI chat-completions provider."""

from __future__ import annotations

from musawiq.ai.providers.base import BaseProvider


class OpenAIProvider(BaseProvider):
    provider = "openai"
    endpoint = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key
        self.model_version = model
        self.available = bool(api_key)


__all__ = ["OpenAIProvider"]
