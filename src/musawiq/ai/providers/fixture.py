"""Deterministic offline AI provider.

Produces a schema-valid Arabic object so the loop can be demonstrated without
network access or a provider key. It never fabricates evidence: list fields are
returned empty, so no issue or recommendation is invented.
"""

from __future__ import annotations

from typing import Any

from musawiq.ai.providers.base import BaseProvider

_ARABIC_TEXT = "تحليل تجريبي باللغة العربية"


def _resolve(spec: Any, root: dict[str, Any]) -> Any:
    if not isinstance(spec, dict):
        return None
    ref = spec.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        name = ref.split("/")[-1]
        return (root.get("$defs") or {}).get(name)
    return spec


def _fixture_value(spec: Any, root: dict[str, Any]) -> Any:
    resolved = _resolve(spec, root)
    if not isinstance(resolved, dict):
        return _ARABIC_TEXT

    enum = resolved.get("enum")
    if isinstance(enum, list) and enum:
        if "inconclusive" in enum:
            return "inconclusive"
        return enum[0]

    variants = resolved.get("anyOf")
    if isinstance(variants, list):
        for variant in variants:
            if _resolve(variant, root) != {"type": "null"}:
                return _fixture_value(variant, root)
        return None

    kind = resolved.get("type")
    if kind == "object" or isinstance(resolved.get("properties"), dict):
        properties = resolved.get("properties") or {}
        required = resolved.get("required") or list(properties)
        return {
            key: _fixture_value(value, root)
            for key, value in properties.items()
            if key in required
        }
    if kind == "array":
        return []
    if kind == "integer":
        return 0
    if kind == "number":
        return 0.5
    if kind == "boolean":
        return True
    return _ARABIC_TEXT


def _fixture_object(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {"result_ar": _ARABIC_TEXT}
    value = _fixture_value(schema, schema)
    return value if isinstance(value, dict) else {"result_ar": _ARABIC_TEXT}


class FixtureProvider(BaseProvider):
    provider = "fixture"
    model_version = "fixture-v1"
    available = True

    def generate_json(
        self, system: str, user: str, schema: dict
    ) -> dict[str, Any]:
        return _fixture_object(schema)


__all__ = ["FixtureProvider"]
