"""AI analysis endpoint behaviour."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import text

from musawiq.ai.client import UnavailableAIClient
from musawiq.ai.providers import FixtureProvider

VALID = {
    "demand": {
        "level": "weak",
        "confidence": 0.8,
        "rationale_ar": "الإشارات ضعيفة لكنها قابلة للتحسين.",
    },
    "issues": [
        {
            "type": "content",
            "severity": "high",
            "metric": "ctr",
            "observed": 0.02,
            "benchmark": 0.03,
            "rationale_ar": "نص الإعلان لا يوضح الفائدة.",
        }
    ],
    "recommendations": [
        {
            "action": "change_copy",
            "target": "ad-1",
            "change_ar": "أعد كتابة العنوان.",
            "expected_impact_ar": "تحسين معدل النقر.",
            "confidence": 0.7,
            "copy_paste_ar": "اكتشف الفرق اليوم.",
        }
    ],
    "next_steps_ar": ["جرّب النص الجديد لأسبوع."],
}


class _ValidFixture(FixtureProvider):
    def generate_json(
        self, system: str, user: str, schema: dict
    ) -> dict[str, Any]:
        return deepcopy(VALID)


class _InvalidFixture(FixtureProvider):
    def generate_json(
        self, system: str, user: str, schema: dict
    ) -> dict[str, Any]:
        return {"demand": {"level": "excellent"}}


def _headers(seed, *, other: bool = False) -> dict[str, str]:
    return {
        "X-Store-Id": str(seed.other_store_id if other else seed.store_id),
        "X-User-Id": str(seed.other_user_id if other else seed.user_id),
        "X-User-Role": "owner",
    }


def test_analysis_persists_and_returns_fixture_demand(
    client, seed, db_engine
) -> None:
    client.app.state.ai_provider = _ValidFixture()

    response = client.post(
        f"/campaigns/{seed.campaign_id}/analyses",
        headers=_headers(seed),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["demand_level"] == "weak"
    assert body["result"]["demand"]["level"] == "weak"
    assert body["input_snapshot"]["concept"]["name"] == "Concept"
    assert body["input_snapshot"]["signals"]["totals"]["clicks"] == 200
    assert body["input_snapshot"]["signals"]["totals"]["ctr"] == 0.02
    assert body["input_snapshot"]["audience"]["segment_count"] == 1

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT status, created_by, prompt_version, provider
                FROM ai_analyses WHERE id = :id
                """
            ),
            {"id": body["id"]},
        ).mappings().one()
    assert row["status"] == "succeeded"
    assert row["created_by"] == seed.user_id
    assert row["prompt_version"] == "analysis-v1"
    assert row["provider"] == "fixture"


def test_degraded_provider_stores_no_invented_issues(
    client, seed, db_engine
) -> None:
    client.app.state.ai_provider = UnavailableAIClient()

    response = client.post(
        f"/campaigns/{seed.campaign_id}/analyses",
        headers=_headers(seed),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "degraded"
    assert body["result"]["degraded_reason"]
    assert "issues" not in body["result"]

    with db_engine.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM ai_analyses WHERE id = :id"),
            {"id": body["id"]},
        ).scalar_one()
    assert status == "degraded"


def test_invalid_provider_json_stores_failed_and_returns_422(
    client, seed, db_engine
) -> None:
    client.app.state.ai_provider = _InvalidFixture()

    response = client.post(
        f"/campaigns/{seed.campaign_id}/analyses",
        headers=_headers(seed),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_analysis"

    with db_engine.connect() as conn:
        status = conn.execute(
            text(
                """
                SELECT status FROM ai_analyses
                WHERE store_id = :store_id
                ORDER BY created_at DESC LIMIT 1
                """
            ),
            {"store_id": seed.store_id},
        ).scalar_one()
    assert status == "failed"


def test_second_store_gets_404(client, seed) -> None:
    client.app.state.ai_provider = _ValidFixture()

    response = client.post(
        f"/campaigns/{seed.campaign_id}/analyses",
        headers=_headers(seed, other=True),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_hourly_analysis_limit_returns_429(
    client, seed, db_engine
) -> None:
    with db_engine.begin() as conn:
        for _ in range(10):
            conn.execute(
                text(
                    """
                    INSERT INTO ai_analyses (
                        store_id, campaign_id, status, input_snapshot,
                        created_by
                    ) VALUES (
                        :store_id, :campaign_id, 'succeeded', '{}'::jsonb,
                        :created_by
                    )
                    """
                ),
                {
                    "store_id": seed.store_id,
                    "campaign_id": seed.campaign_id,
                    "created_by": seed.user_id,
                },
            )

    client.app.state.ai_provider = _ValidFixture()
    response = client.post(
        f"/campaigns/{seed.campaign_id}/analyses",
        headers=_headers(seed),
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
