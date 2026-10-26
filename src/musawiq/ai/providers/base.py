"""Base AI provider with shared HTTP and JSON extraction."""

from __future__ import annotations

import json
from typing import Any

import httpx

REQUEST_TIMEOUT_SECONDS = 30.0
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_ATTEMPTS = 2


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class BaseProvider:
    available: bool = True
    provider: str = "base"
    model_version: str = ""
    endpoint: str = ""
    api_key: str = ""

    def generate_json(
        self, system: str, user: str, schema: dict
    ) -> dict[str, Any]:
        if not self.available:
            raise ProviderError(f"{self.provider} is unavailable")
        response = self._post_json(
            self.endpoint, self._chat_payload(system, user)
        )
        return self._extract_json(response)

    def _chat_payload(self, system: str, user: str) -> dict[str, Any]:
        return {
            "model": self.model_version,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }

    def _post_json(
        self, url: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        for attempt in range(MAX_ATTEMPTS):
            try:
                with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                    response = client.post(url, json=payload, headers=headers)
            except httpx.TimeoutException as exc:
                if attempt + 1 < MAX_ATTEMPTS:
                    continue
                raise ProviderError(
                    f"{self.provider} request timed out"
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderError(
                    f"{self.provider} request failed"
                ) from exc

            if response.status_code >= 500 and attempt + 1 < MAX_ATTEMPTS:
                continue
            if response.status_code >= 400:
                raise ProviderError(
                    f"{self.provider} returned HTTP {response.status_code}",
                    status_code=response.status_code,
                )
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise ProviderError(
                    f"{self.provider} response exceeded the size limit"
                )
            try:
                return response.json()
            except ValueError as exc:
                raise ProviderError(
                    f"{self.provider} returned invalid JSON"
                ) from exc

        raise ProviderError(f"{self.provider} request failed")

    def _extract_json(self, response: Any) -> dict[str, Any]:
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                f"{self.provider} returned an unexpected response"
            ) from exc

        if isinstance(content, dict):
            return content
        if not isinstance(content, str):
            raise ProviderError(
                f"{self.provider} returned non-text JSON content"
            )
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"{self.provider} returned invalid JSON content"
            ) from exc
        if not isinstance(parsed, dict):
            raise ProviderError(
                f"{self.provider} returned JSON that is not an object"
            )
        return parsed


__all__ = [
    "BaseProvider",
    "MAX_ATTEMPTS",
    "MAX_RESPONSE_BYTES",
    "ProviderError",
    "REQUEST_TIMEOUT_SECONDS",
]
