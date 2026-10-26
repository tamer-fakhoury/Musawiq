"""Groq OpenAI-compatible provider."""

from __future__ import annotations

from musawiq.ai.providers.base import BaseProvider


class GroqProvider(BaseProvider):
    provider = "groq"
    endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(
        self, api_key: str, model: str = "llama-3.3-70b-versatile"
    ) -> None:
        self.api_key = api_key
        self.model_version = model
        self.available = bool(api_key)


__all__ = ["GroqProvider"]
