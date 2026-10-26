"""AI provider selection and payload contracts."""

from __future__ import annotations

import json
import logging

from musawiq.ai.client import UnavailableAIClient
from musawiq.ai.providers.base import BaseProvider
from musawiq.ai.providers.factory import get_provider
from musawiq.ai.providers.fixture import FixtureProvider
from musawiq.ai.providers.groq import GroqProvider
from musawiq.ai.providers.openai import OpenAIProvider
from musawiq.config import Settings


def _settings(**overrides) -> Settings:
    values = {
        "database_url": "postgresql+psycopg://test:test@127.0.0.1:1/test"
    }
    values.update(overrides)
    return Settings(**values)


def test_factory_defaults_to_groq() -> None:
    provider = get_provider(_settings(groq_api_key="test-groq-key"))

    assert isinstance(provider, GroqProvider)
    assert provider.available is True
    assert provider.provider == "groq"
    assert provider.model_version == "llama-3.3-70b-versatile"


def test_missing_key_degrades(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="musawiq.ai.providers"):
        provider = get_provider(
            _settings(ai_provider="groq", groq_api_key=None)
        )

    assert isinstance(provider, UnavailableAIClient)
    assert provider.available is False
    assert provider.provider == "unavailable"
    assert "unavailable" in caplog.text.lower()
    assert "test-groq-key" not in caplog.text


def test_fixture_returns_valid_arabic_json() -> None:
    schema = {
        "type": "object",
        "properties": {
            "demand_level": {"type": "string"},
            "summary_ar": {"type": "string"},
            "issues": {"type": "array"},
            "confidence": {"type": "number"},
        },
    }

    result = FixtureProvider().generate_json("system", "user", schema)

    assert set(result) == {
        "demand_level",
        "summary_ar",
        "issues",
        "confidence",
    }
    assert isinstance(result["demand_level"], str)
    assert any(
        "\u0600" <= character <= "\u06ff"
        for character in result["demand_level"]
    )
    assert isinstance(result["issues"], list)
    assert isinstance(result["confidence"], (int, float))
    assert json.loads(json.dumps(result)) == result


def test_provider_payloads_and_models(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    def fake_post(self, url, payload):
        calls.append((url, payload))
        return {"choices": [{"message": {"content": '{"result":"ok"}'}}]}

    monkeypatch.setattr(BaseProvider, "_post_json", fake_post)

    openai = OpenAIProvider("openai-key", "gpt-4o-mini")
    groq = GroqProvider("groq-key", "llama-3.3-70b-versatile")

    assert openai.generate_json("sys", "user", {}) == {"result": "ok"}
    assert groq.generate_json("sys", "user", {}) == {"result": "ok"}

    assert calls[0][0] == "https://api.openai.com/v1/chat/completions"
    assert calls[1][0] == "https://api.groq.com/openai/v1/chat/completions"
    assert calls[0][1]["model"] == "gpt-4o-mini"
    assert calls[1][1]["model"] == "llama-3.3-70b-versatile"
    for _, payload in calls:
        assert payload["messages"] == [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "user"},
        ]
        assert payload["response_format"] == {"type": "json_object"}
