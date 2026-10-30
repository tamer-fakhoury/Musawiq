"""FR-3.2.4: campaign tracking links and publication gate."""

from __future__ import annotations

import uuid
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import text


def _headers(tenant) -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": "owner",
    }


def _seed_landing_page(db_engine, tenant):
    with db_engine.begin() as conn:
        concept_id = conn.execute(
            text("SELECT product_concept_id FROM tests WHERE id = :id"),
            {"id": tenant.test_id},
        ).scalar_one()
        template_id = conn.execute(
            text(
                """
                INSERT INTO page_templates (key, version, name, schema)
                VALUES (:key, 1, 'Tracking', '{"schema_version": 1}'::jsonb)
                RETURNING id
                """
            ),
            {"key": f"tracking-{uuid.uuid4().hex[:8]}"},
        ).scalar_one()
        slug = f"tracking-{uuid.uuid4().hex[:8]}"
        conn.execute(
            text(
                """
                INSERT INTO landing_pages (
                    store_id, product_concept_id, test_id, slug, status,
                    template_id, language, currency, published_url
                ) VALUES (
                    :store_id, :concept_id, :test_id, :slug, 'published',
                    :template_id, 'en', 'USD', :url
                )
                """
            ),
            {
                "store_id": tenant.store_id,
                "concept_id": concept_id,
                "test_id": tenant.test_id,
                "slug": slug,
                "template_id": template_id,
                "url": f"https://pages.musawiq.app/p/{slug}",
            },
        )
        return f"https://pages.musawiq.app/p/{slug}"


def _campaign_and_variation(client, tenant, destination="https://example.com/raw"):
    campaign = client.post(
        "/campaigns",
        json={
            "test_id": str(tenant.test_id),
            "provider": "meta",
            "name": "Tracking Campaign",
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
        json={
            "name": "Ad Set",
            "targeting": {"schema_version": 1, "locations": ["SA"]},
        },
        headers=_headers(tenant),
    )
    assert adset.status_code == 201
    adset_id = adset.json()["id"]
    variation = client.post(
        f"/campaigns/{campaign_id}/variations",
        json={
            "adset_id": adset_id,
            "copy_text": "Fresh coffee every morning",
            "headline": "Coffee",
            "destination_url": destination,
        },
        headers=_headers(tenant),
    )
    assert variation.status_code == 201
    return campaign_id, adset_id, variation.json()["id"]


def test_tracking_link_embeds_utm_and_updates_variation(
    client, tenant, db_engine
):
    landing_url = _seed_landing_page(db_engine, tenant)
    campaign_id, adset_id, variation_id = _campaign_and_variation(client, tenant)

    response = client.post(
        f"/campaigns/{campaign_id}/tracking-links",
        json={"adset_id": adset_id, "ad_variation_id": variation_id},
        headers=_headers(tenant),
    )

    assert response.status_code == 201
    link = response.json()
    assert link["token"].startswith("tl_")
    parts = urlsplit(link["destination_url"])
    query = parse_qs(parts.query)
    assert link["destination_url"].startswith(landing_url)
    assert query["utm_source"] == ["musawiq"]
    assert query["utm_medium"] == ["paid_social"]
    assert query["utm_campaign"]
    assert query["tk"] == [link["token"]]

    detail = client.get(f"/campaigns/{campaign_id}", headers=_headers(tenant))
    variation = detail.json()["ad_sets"][0]["variations"][0]
    assert variation["destination_url"] == link["destination_url"]


def test_association_is_visible_on_campaign_detail(client, tenant, db_engine):
    _seed_landing_page(db_engine, tenant)
    campaign_id, adset_id, variation_id = _campaign_and_variation(client, tenant)
    client.post(
        f"/campaigns/{campaign_id}/tracking-links",
        json={"adset_id": adset_id, "ad_variation_id": variation_id},
        headers=_headers(tenant),
    )

    detail = client.get(f"/campaigns/{campaign_id}", headers=_headers(tenant))

    assert detail.status_code == 200
    body = detail.json()
    assert body["product"]["id"]
    assert len(body["landing_pages"]) == 1
    assert len(body["tracking_links"]) == 1
    assert body["tracking_links"][0]["token"] in (
        body["ad_sets"][0]["variations"][0]["destination_url"]
    )


def test_campaign_requires_exactly_one_landing_page(client, tenant):
    campaign_id, adset_id, variation_id = _campaign_and_variation(client, tenant)

    response = client.post(
        f"/campaigns/{campaign_id}/tracking-links",
        json={"adset_id": adset_id, "ad_variation_id": variation_id},
        headers=_headers(tenant),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "landing_page_required"


def test_publication_blocked_until_tracking_is_valid(client, tenant, db_engine):
    _seed_landing_page(db_engine, tenant)
    campaign_id, adset_id, variation_id = _campaign_and_variation(client, tenant)

    blocked = client.post(
        f"/campaigns/{campaign_id}/publication-check",
        json={"adset_id": adset_id, "ad_variation_id": variation_id},
        headers=_headers(tenant),
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "tracking_invalid"

    client.post(
        f"/campaigns/{campaign_id}/tracking-links",
        json={"adset_id": adset_id, "ad_variation_id": variation_id},
        headers=_headers(tenant),
    )
    allowed = client.post(
        f"/campaigns/{campaign_id}/publication-check",
        json={"adset_id": adset_id, "ad_variation_id": variation_id},
        headers=_headers(tenant),
    )
    assert allowed.status_code == 200
    assert allowed.json() == {"valid": True, "errors": []}
