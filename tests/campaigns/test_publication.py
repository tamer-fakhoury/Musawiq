"""FR-3.2.7: campaign publication, idempotency, and error mapping."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from musawiq.auth.errors import PermissionDenied


def _headers(tenant, role="owner") -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": role,
    }


def _seed_ready_campaign(client, tenant, db_engine):
    with db_engine.begin() as conn:
        concept_id = conn.execute(
            text("SELECT product_concept_id FROM tests WHERE id = :id"),
            {"id": tenant.test_id},
        ).scalar_one()
        template_id = conn.execute(
            text(
                """
                INSERT INTO page_templates (key, version, name, schema)
                VALUES (:key, 1, 'Publish', '{"schema_version": 1}'::jsonb)
                RETURNING id
                """
            ),
            {"key": f"publish-{uuid.uuid4().hex[:8]}"},
        ).scalar_one()
        slug = f"publish-{uuid.uuid4().hex[:8]}"
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
        conn.execute(
            text(
                """
                INSERT INTO ad_account_connections (
                    store_id, provider, external_account_id, status,
                    token_expires_at
                ) VALUES (
                    :store_id, 'meta', :external_id, 'connected',
                    now() + interval '30 days'
                )
                """
            ),
            {
                "store_id": tenant.store_id,
                "external_id": f"act-{uuid.uuid4().hex[:8]}",
            },
        )

    campaign = client.post(
        "/campaigns",
        json={
            "test_id": str(tenant.test_id),
            "provider": "meta",
            "name": "Publish Campaign",
            "objective": "conversions",
            "budget_type": "daily",
            "budget_minor": 5000,
            "currency": "USD",
            "start_at": "2026-01-01T00:00:00Z",
            "end_at": "2026-01-31T00:00:00Z",
        },
        headers=_headers(tenant),
    ).json()
    adset = client.post(
        f"/campaigns/{campaign['id']}/adsets",
        json={
            "name": "Ad Set",
            "targeting": {"schema_version": 1, "locations": ["SA"]},
        },
        headers=_headers(tenant),
    ).json()
    variation = client.post(
        f"/campaigns/{campaign['id']}/variations",
        json={
            "adset_id": adset["id"],
            "copy_text": "Fresh coffee every morning",
            "headline": "Coffee",
            "destination_url": "https://example.com/raw",
        },
        headers=_headers(tenant),
    ).json()
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
            {"file_id": file_id, "id": variation["id"]},
        )
    client.patch(
        f"/ad-variations/{variation['id']}",
        json={"status": "approved"},
        headers=_headers(tenant),
    )
    client.post(
        f"/campaigns/{campaign['id']}/tracking-links",
        json={"adset_id": adset["id"], "ad_variation_id": variation["id"]},
        headers=_headers(tenant),
    )
    return campaign["id"]


def _publish(client, tenant, campaign_id, *, confirm=True, role="owner"):
    return client.post(
        f"/campaigns/{campaign_id}/publish",
        json={"confirm": confirm},
        headers=_headers(tenant, role=role),
    )


def test_publish_requires_explicit_approval_and_role(client, tenant, db_engine):
    campaign_id = _seed_ready_campaign(client, tenant, db_engine)

    unconfirmed = _publish(client, tenant, campaign_id, confirm=False)
    assert unconfirmed.status_code == 422
    assert unconfirmed.json()["error"]["code"] == "approval_required"

    with pytest.raises(PermissionDenied):
        _publish(client, tenant, campaign_id, role="analyst")

