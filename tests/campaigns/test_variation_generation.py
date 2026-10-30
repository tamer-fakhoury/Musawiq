"""FR-3.2.1: ad copy variation generation."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from musawiq.services.ad_variations import PLATFORM_LIMITS


class StubProvider:
    available = True
    model_version = "stub-v1"

    def __init__(self, variations: list[dict[str, str]]) -> None:
        self.variations = variations
        self.prompts: list[str] = []

    def generate_json(self, system: str, user: str, schema: dict) -> dict:
        self.prompts.append(user)
        return {"variations": self.variations}


def _headers(tenant) -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": "owner",
    }


def _variation(index: int, body: str | None = None) -> dict[str, str]:
    return {
        "name": f"Variation {index}",
        "headline": f"Headline {index}",
        "copy_text": body or f"Fresh coffee angle number {index}",
        "description": f"Description {index}",
    }


def _seed_landing_page(db_engine, tenant, *, language="ar"):
    with db_engine.begin() as conn:
        concept_id = conn.execute(
            text("SELECT product_concept_id FROM tests WHERE id = :id"),
            {"id": tenant.test_id},
        ).scalar_one()
        template_id = conn.execute(
            text(
                """
                INSERT INTO page_templates (key, version, name, schema)
                VALUES (:key, 1, 'Meta', '{"schema_version": 1}'::jsonb)
                RETURNING id
                """
            ),
            {"key": f"meta-{uuid.uuid4().hex[:8]}"},
        ).scalar_one()
        url = f"https://pages.musawiq.app/p/{uuid.uuid4().hex[:8]}"
        conn.execute(
            text(
                """
                INSERT INTO landing_pages (
                    store_id, product_concept_id, test_id, slug, status,
                    template_id, language, currency, published_url
                ) VALUES (
                    :store_id, :concept_id, :test_id, :slug, 'draft',
                    :template_id, :language, 'USD', :url
                )
                """
            ),
            {
                "store_id": tenant.store_id,
                "concept_id": concept_id,
                "test_id": tenant.test_id,
                "slug": url.rsplit("/", 1)[-1],
                "template_id": template_id,
                "language": language,
                "url": url,
            },
        )
    return url


def _campaign_and_adset(client, tenant):
    campaign = client.post(
        "/campaigns",
        json={
            "test_id": str(tenant.test_id),
            "provider": "meta",
            "name": "Variation Campaign",
            "objective": "conversions",
            "budget_type": "daily",
            "budget_minor": 5000,
            "currency": "USD",
            "start_at": "2026-01-01T00:00:00Z",
            "end_at": "2026-01-31T00:00:00Z",
        },
        headers=_headers(tenant),
    )
    assert campaign.status_code == 201
    campaign_id = campaign.json()["id"]
    adset = client.post(
        f"/campaigns/{campaign_id}/adsets",
        json={"name": "Ad Set", "targeting": {"country": "SA"}},
        headers=_headers(tenant),
    )
    assert adset.status_code == 201
    return campaign_id, adset.json()["id"]


def _generate(client, tenant, campaign_id, adset_id, count=3):
    return client.post(
        f"/campaigns/{campaign_id}/variations/generate",
        json={"adset_id": adset_id, "count": count},
        headers=_headers(tenant),
    )


def test_generates_requested_count_linked_to_product_and_page(
    client, tenant, db_engine
):
    published_url = _seed_landing_page(db_engine, tenant)
    campaign_id, adset_id = _campaign_and_adset(client, tenant)
    client.app.state.ai_provider = StubProvider(
        [_variation(1), _variation(2)]
    )

    response = _generate(client, tenant, campaign_id, adset_id, count=2)

    assert response.status_code == 201
    variations = response.json()["variations"]
    assert len(variations) == 2
    assert all(item["status"] == "draft" for item in variations)
    assert all(item["adset_id"] == adset_id for item in variations)
    assert all(item["destination_url"] == published_url for item in variations)

    with db_engine.connect() as conn:
        linked = conn.execute(
            text(
                """
                SELECT count(*) FROM ad_variations AS v
                JOIN ad_sets AS s ON s.id = v.adset_id
                JOIN campaigns AS c ON c.id = s.campaign_id
                WHERE c.test_id = :test_id AND v.store_id = :store_id
                """
            ),
            {"test_id": tenant.test_id, "store_id": tenant.store_id},
        ).scalar_one()
    assert linked == 2


def test_respects_platform_limits_and_campaign_language(
    client, tenant, db_engine
):
    _seed_landing_page(db_engine, tenant, language="ar")
    campaign_id, adset_id = _campaign_and_adset(client, tenant)
    long_text = "قهوة " * 100
    stub = StubProvider(
        [
            {
                "name": "V" * 300,
                "headline": "H" * 100,
                "copy_text": long_text,
                "description": "D" * 300,
            }
        ]
    )
    client.app.state.ai_provider = stub

    response = _generate(client, tenant, campaign_id, adset_id, count=1)

    assert response.status_code == 201
    limits = PLATFORM_LIMITS["meta"]
    variation = response.json()["variations"][0]
    assert len(variation["name"]) <= limits["name"]
    assert len(variation["headline"]) <= limits["headline"]
    assert len(variation["copy_text"]) <= limits["copy_text"]
    assert len(variation["description"]) <= limits["description"]

    prompt = json.loads(stub.prompts[0].split("Context JSON:\n", 1)[1])
    assert prompt["language"] == "ar"
    assert prompt["character_limits"] == limits


def test_near_duplicates_are_flagged(client, tenant, db_engine):
    _seed_landing_page(db_engine, tenant)
    campaign_id, adset_id = _campaign_and_adset(client, tenant)
    repeated = "Rich espresso taste at home every single morning"
    client.app.state.ai_provider = StubProvider(
        [
            _variation(1, repeated),
            _variation(2, repeated),
            _variation(3, "Quick brewing for busy office teams"),
        ]
    )

    response = _generate(client, tenant, campaign_id, adset_id, count=3)

    assert response.status_code == 201
    variations = response.json()["variations"]
    assert variations[0]["near_duplicate"] is False
    assert variations[1]["near_duplicate"] is True
    assert variations[1]["duplicate_of"] == variations[0]["id"]
    assert variations[2]["near_duplicate"] is False


def test_claim_filter_rejects_generated_variations(client, tenant, db_engine):
    _seed_landing_page(db_engine, tenant)
    campaign_id, adset_id = _campaign_and_adset(client, tenant)
    client.app.state.ai_provider = StubProvider(
        [_variation(1, "نتائج مضمونة لكل عميل")]
    )

    response = _generate(client, tenant, campaign_id, adset_id, count=1)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "claim_rejected"

    with db_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM ad_variations "
                "WHERE adset_id = :id AND store_id = :store_id"
            ),
            {"id": adset_id, "store_id": tenant.store_id},
        ).scalar_one()
    assert count == 0
