"""AI copy suggestion contracts."""

from __future__ import annotations

ARABIC_COPY = "قهوة مختصة تصلك حتى بابك"
ARABIC_HEADLINE = "عرض خاص اليوم"
ARABIC_DESCRIPTION = "اطلب الآن واستمتع بالطعم"
ARABIC_ANGLE = "الراحة والجودة"


class RecordingProvider:
    available = True
    provider = "fixture"
    model_version = "fixture-copy-v1"

    def __init__(self, count: int) -> None:
        self.count = count
        self.system: str | None = None
        self.user: str | None = None
        self.schema: dict | None = None

    def generate_json(self, system: str, user: str, schema: dict) -> dict:
        self.system = system
        self.user = user
        self.schema = schema
        return {
            "variants": [
                {
                    "headline": ARABIC_HEADLINE,
                    "copy_text": ARABIC_COPY,
                    "description": ARABIC_DESCRIPTION,
                    "angle_ar": ARABIC_ANGLE,
                }
                for _ in range(self.count)
            ]
        }


class DegradedProvider:
    available = False
    provider = "unavailable"
    degraded_reason = "The AI provider is unavailable. No content was generated."


class InvalidProvider:
    available = True
    provider = "fixture"
    model_version = "fixture-copy-v1"

    def generate_json(self, system: str, user: str, schema: dict) -> dict:
        return {"variants": [{"headline": ARABIC_HEADLINE}]}


def _headers(context) -> dict[str, str]:
    return {
        "X-Store-Id": str(context.store_id),
        "X-User-Id": str(context.user_id),
        "X-User-Role": "owner",
    }


def test_suggest_returns_requested_arabic_variants(
    client, copy_context
) -> None:
    provider = RecordingProvider(count=2)
    client.app.state.ai_provider = provider

    response = client.post(
        f"/campaigns/{copy_context.campaign_id}/variations/suggest",
        json={
            "adset_id": str(copy_context.adset_id),
            "count": 2,
            "notes": "نسخة مختلفة عن الحالية",
        },
        headers=_headers(copy_context),
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"variants"}
    assert len(body["variants"]) == 2
    for variant in body["variants"]:
        assert set(variant) == {
            "headline",
            "copy_text",
            "description",
            "angle_ar",
        }
        assert all(value.strip() for value in variant.values())
        assert any("\u0600" <= char <= "\u06ff" for char in variant["copy_text"])

    assert "Modern Standard Arabic" in provider.system
    assert "strict JSON" in provider.system
    assert "medical" in provider.system
    assert "guaranteed" in provider.system
    assert "Write exactly 2" in provider.user

    detail = client.get(
        f"/campaigns/{copy_context.campaign_id}",
        headers=_headers(copy_context),
    )
    variations = detail.json()["ad_sets"][0]["variations"]
    assert len(variations) == 1


def test_degraded_provider_returns_503_envelope(
    client, copy_context
) -> None:
    client.app.state.ai_provider = DegradedProvider()

    response = client.post(
        f"/campaigns/{copy_context.campaign_id}/variations/suggest",
        json={"count": 3},
        headers=_headers(copy_context),
    )

    assert response.status_code == 503
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "ai_unavailable"
    assert body["error"]["correlation_id"] == response.headers["X-Correlation-ID"]
    assert "variants" not in body


def test_invalid_provider_json_returns_502_envelope(
    client, copy_context
) -> None:
    client.app.state.ai_provider = InvalidProvider()

    response = client.post(
        f"/campaigns/{copy_context.campaign_id}/variations/suggest",
        json={"count": 1},
        headers=_headers(copy_context),
    )

    assert response.status_code == 502
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "ai_invalid_output"
    assert body["error"]["correlation_id"] == response.headers["X-Correlation-ID"]
    assert "variants" not in body
