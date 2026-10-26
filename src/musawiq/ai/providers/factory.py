"""Provider selection from application settings."""

from __future__ import annotations

import logging

from musawiq.ai.client import UnavailableAIClient
from musawiq.ai.providers.base import BaseProvider
from musawiq.ai.providers.fixture import FixtureProvider
from musawiq.ai.providers.groq import GroqProvider
from musawiq.ai.providers.openai import OpenAIProvider
from musawiq.config import Settings, get_settings

logger = logging.getLogger("musawiq.ai.providers")


def get_provider(
    settings: Settings | None = None,
) -> BaseProvider | UnavailableAIClient:
    settings = settings or get_settings()
    name = (settings.ai_provider or "groq").strip().lower()

    if name == "fixture":
        return FixtureProvider()

    if name == "groq":
        if not settings.groq_api_key:
            logger.warning(
                "AI provider 'groq' is unavailable: "
                "MUSAWIQ_GROQ_API_KEY is not set"
            )
            return UnavailableAIClient()
        return GroqProvider(settings.groq_api_key, settings.groq_model)

    if name == "openai":
        if not settings.openai_api_key:
            logger.warning(
                "AI provider 'openai' is unavailable: "
                "MUSAWIQ_OPENAI_API_KEY is not set"
            )
            return UnavailableAIClient()
        return OpenAIProvider(settings.openai_api_key, settings.openai_model)

    logger.warning(
        "Unknown AI provider %r; using the degraded provider", name
    )
    return UnavailableAIClient()


__all__ = ["get_provider"]
