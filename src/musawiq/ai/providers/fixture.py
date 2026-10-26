"""Deterministic offline AI provider."""

from __future__ import annotations

from typing import Any

from musawiq.ai.providers.base import BaseProvider

_ARABIC_TEXT = "نتيجة تحليل تجريبية"


def _fixture_value(spec: Any) -> Any:
    if isinstance(spec, dict):
        properties = spec.get("properties")
        if isinstance(properties, dict):
            return {
                key: _fixture_value(value)
                for key, value in properties.items()
            }
        kind = spec.get("type")
        if kind == "array":
            return []
        if kind == "object":
            return {}
        if kind == "integer":
            return 0
        if kind == "number":
            return 0.5
        if kind == "boolean":
            return True
    return _ARABIC_TEXT


def _fixture_object(schema: Any) -> dict[str, Any]:
    if isinstance(schema, dict) and isinstance(schema.get("properties"), dict):
        return {
            key: _fixture_value(value)
            for key, value in schema["properties"].items()
        }
    if isinstance(schema, dict) and schema.get("type") == "object":
        return {}
    if isinstance(schema, dict):
        return {key: _fixture_value(value) for key, value in schema.items()}
    return {"result_ar": _ARABIC_TEXT}


class FixtureProvider(BaseProvider):
    provider = "fixture"
    model_version = "fixture-v1"
    available = True

    def generate_json(
        self, system: str, user: str, schema: dict
    ) -> dict[str, Any]:
        return _fixture_object(schema)


__all__ = ["FixtureProvider"]
