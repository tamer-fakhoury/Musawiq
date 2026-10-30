"""FR-3.2.5: pre-flight validation and ad preview."""

from __future__ import annotations

import uuid

from sqlalchemy import text


def _headers(tenant) -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": "owner",
    }


def _connect_account(db_engine, tenant, *, expired=False):
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO ad_account_connections (
                    store_id, provider, external_account_id, status,
                    token_expires_at
                ) VALUES (
                    :store_id, 'meta', :external_id, 'connected',
                    CASE WHEN :expired THEN now() - interval '1 day'
                         ELSE now() + interval '30 days' END
                )
                """
            ),
            {
                "store_id": tenant.store_id,
                "external_id": f"act-{uuid.uuid4().hex[:8]}",
                "expired": expired,
            },
        )


def _seed_landing_page(db_engine, tenant, *, status="published"):
    with db_engine.begin() as conn:
        concept_id = conn.execute(
            text("SELECT product_concept_id FROM tests WHERE id = :id"),
            {"id": tenant.test_id},
        ).scalar_one()
        template_id = conn.execute(
            text(
                """
                INSERT INTO page_templates (key, version, name, schema)
                VALUES (:key, 1, 'Preflight', '{"schema_version": 1}'::jsonb)
                RETURNING id
                """
            ),
            {"key": f"preflight-{uuid.uuid4().hex[:8]}"},
        ).scalar_one()
        slug = f"preflight-{uuid.uuid4().hex[:8]}"
        conn.execute(
            text(
                """
                INSERT INTO landing_pages (
                    store_id, product_concept_id, test_id, slug, status,
                    template_id, language, currency, published_url
                ) VALUES (
                    :store_id, :concept_id, :test_id, :slug, :status,
                    :template_id, 'en', 'USD', :url
                )
                """
            ),
            {
                "store_id": tenant.store_id,
                "concept_id": concept_id,
                "test_id": tenant.test_id,
                "slug": slug,
                "status": status,
                "template_id": template_id,
                "url": (
                    f"https://pages.musawiq.app/p/{slug}"
                    if status == "published"
                    else None
                ),
            },
        )


def _campaign_and_variation(client, tenant):
    campaign = client.post(
        "/campaigns",
        json={
            "test_id": str(tenant.test_id),
            "provider": "meta",
            "name": "Preflight Campaign",
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
            "destination_url": "https://example.com/raw",
        },
        headers=_headers(tenant),
    )
    assert variation.status_code == 201
    return campaign_id, adset_id, variation.json()["id"]


def _attach_creative(db_engine, tenant, variation_id):
    with db_engine.begin() as conn:
        file_id = conn.execute(
            text(
                """
                INSERT INTO stored_files (
                    store_id, purpose, original_filename, mime_type,
                    size_bytes, checksum_sha256, storage_provider,
                    storage_key, status, uploaded_by_user_id
                ) VALUES (
                    :store_id, 'product_image', 'creative.png', 'image/png',
                    10, repeat('a', 64), 'local', :key, 'committed',
                    :user_id
                )
                RETURNING id
                """
            ),
            {
                "store_id": tenant.store_id,
                "key": uuid.uuid4().hex,
                "user_id": tenant.user_id,
            },
        ).scalar_one()
        conn.execute(
            text(
                "UPDATE ad_variations SET creative_file_id = :file_id "
                "WHERE id = :id"
            ),
            {"file_id": file_id, "id": variation_id},
        )


def _approve(client, tenant, variation_id):
    response = client.patch(
        f"/ad-variations/{variation_id}",
        json={"status": "approved"},
        headers=_headers(tenant),
    )
    assert response.status_code == 200


def _preflight(client, tenant, campaign_id):
    return client.get(
        f"/campaigns/{campaign_id}/preflight", headers=_headers(tenant)
    )


def test_preflight_passes_and_returns_ad_preview(client, tenant, db_engine):
    _seed_landing_page(db_engine, tenant)
    _connect_account(db_engine, tenant)
    campaign_id, adset_id, variation_id = _campaign_and_variation(client, tenant)
    _attach_creative(db_engine, tenant, variation_id)
    _approve(client, tenant, variation_id)
    link = client.post(
        f"/campaigns/{campaign_id}/tracking-links",
        json={"adset_id": adset_id, "ad_variation_id": variation_id},
        headers=_headers(tenant),
    )
    assert link.status_code == 201

    response = _preflight(client, tenant, campaign_id)

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["unresolved"] == []

    preview = body["preview"]
    assert len(preview["variations"]) == 1
    item = preview["variations"][0]
    assert item["headline"] == "Coffee"
    assert item["copy_text"] == "Fresh coffee every morning"
    assert item["destination_url"] == link.json()["destination_url"]
    assert item["creative"]["filename"] == "creative.png"


def test_preflight_lists_account_budget_page_and_variation_blockers(
    client, tenant, db_engine
):
    _seed_landing_page(db_engine, tenant, status="draft")
    campaign_id, _, _ = _campaign_and_variation(client, tenant)
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE campaigns SET budget_minor = 10 WHERE id = :id"),
            {"id": campaign_id},
        )

    response = _preflight(client, tenant, campaign_id)

    body = response.json()
    assert body["valid"] is False
    codes = {item["code"] for item in body["unresolved"]}
    assert {
        "account_not_connected",
        "budget_below_minimum",
        "landing_page_not_published",
        "no_approved_variation",
    } <= codes
    assert body["preview"]["variations"] == []


def test_preflight_flags_creative_and_tracking_for_approved_variation(
    client, tenant, db_engine
):
    _seed_landing_page(db_engine, tenant)
    _connect_account(db_engine, tenant, expired=True)
    campaign_id, _, variation_id = _campaign_and_variation(client, tenant)
    _approve(client, tenant, variation_id)

    response = _preflight(client, tenant, campaign_id)

    body = response.json()
    assert body["valid"] is False
    codes = {item["code"] for item in body["unresolved"]}
    assert {"account_token_expired", "creative_missing", "tracking_invalid"} <= codes
    item = body["preview"]["variations"][0]
    assert item["creative"] is None
    assert item["variation_id"] == variation_id
