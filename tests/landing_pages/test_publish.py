"""FR-3.1.5: preview, publish, unpublish, and public URL."""

from __future__ import annotations

from sqlalchemy import text

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _headers(tenant) -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": "owner",
    }


def _payload(tenant, **overrides):
    payload = {
        "product_concept_id": str(tenant.concept_id),
        "name": "Coffee Maker",
        "description": "Compact espresso machine",
        "price_minor": 4999,
        "currency": "USD",
        "language": "ar",
        "target_market": "SA",
        "image_file_ids": [],
        "order_method": {"type": "whatsapp", "whatsapp_number": "+966500000000"},
    }
    payload.update(overrides)
    return payload


def _setup(client, tenant):
    created = client.post(
        "/landing-pages/drafts", json=_payload(tenant), headers=_headers(tenant)
    )
    assert created.status_code == 201
    page_id = created.json()["id"]
    channel = client.put(
        f"/landing-pages/{page_id}/order-channel",
        json={
            "type": "whatsapp",
            "whatsapp_number": "+966500000000",
            "whatsapp_message_template": "أريد الطلب",
        },
        headers=_headers(tenant),
    )
    assert channel.status_code == 200
    return page_id


def _publish(client, tenant, page_id, confirm=True):
    return client.post(
        f"/landing-pages/{page_id}/publish",
        json={"confirm": confirm},
        headers=_headers(tenant),
    )


def test_preview_offers_mobile_and_desktop_views_with_alt_text(client, tenant):
    page_id = _setup(client, tenant)
    image = client.post(
        "/landing-pages/images",
        files={"file": ("product.png", PNG_BYTES, "image/png")},
        headers=_headers(tenant),
    )
    image_id = image.json()["id"]
    client.put(
        f"/landing-pages/{page_id}/draft",
        json=_payload(tenant, image_file_ids=[image_id]),
        headers=_headers(tenant),
    )

    preview = client.get(
        f"/landing-pages/{page_id}/preview", headers=_headers(tenant)
    )

    assert preview.status_code == 200
    body = preview.json()
    assert body["views"]["mobile"]["columns"] == 1
    assert body["views"]["desktop"]["columns"] == 2
    assert body["content"]["images"][0]["alt"] == "Coffee Maker"
    assert body["direction"] == "rtl"


def test_publish_requires_confirmation_and_valid_fields(client, tenant):
    page_id = _setup(client, tenant)

    unconfirmed = _publish(client, tenant, page_id, confirm=False)
    assert unconfirmed.status_code == 422
    assert unconfirmed.json()["error"]["code"] == "confirmation_required"

    missing_channel = client.post(
        "/landing-pages/drafts", json=_payload(tenant), headers=_headers(tenant)
    )
    bare_id = missing_channel.json()["id"]
    invalid = _publish(client, tenant, bare_id)
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "publish_invalid"


def test_publish_returns_https_url_serves_publicly_and_unpublishes(
    client, tenant, db_engine
):
    page_id = _setup(client, tenant)
    published = _publish(client, tenant, page_id)

    assert published.status_code == 200
    body = published.json()
    assert body["status"] == "published"
    assert body["published_at"] is not None
    assert body["published_url"].startswith("https://")
    assert body["published_url"].endswith(body["slug"])

    with db_engine.connect() as conn:
        audit = conn.execute(
            text(
                "SELECT count(*) FROM audit_logs "
                "WHERE action = 'landing_page.publish' AND target_id = :id"
            ),
            {"id": page_id},
        ).scalar_one()
    assert audit == 1

    public = client.get(f"/p/{body['slug']}")
    assert public.status_code == 200
    assert public.json()["content"]["product"]["name"] == "Coffee Maker"

    unpublished = client.post(
        f"/landing-pages/{page_id}/unpublish", headers=_headers(tenant)
    )
    assert unpublished.status_code == 200
    assert unpublished.json()["status"] == "unpublished"

    gone = client.get(f"/p/{body['slug']}")
    assert gone.status_code == 404
    assert gone.json()["error"]["code"] == "page_unavailable"


def test_update_published_page_creates_new_version_and_republishes(
    client, tenant
):
    page_id = _setup(client, tenant)
    first = _publish(client, tenant, page_id).json()

    updated = client.put(
        f"/landing-pages/{page_id}/draft",
        json=_payload(tenant, name="Coffee Maker Pro"),
        headers=_headers(tenant),
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["status"] == "published"
    assert body["draft_version"] == 2
    assert body["published_url"] == first["published_url"]

    public = client.get(f"/p/{body['slug']}")
    assert public.json()["content"]["product"]["name"] == "Coffee Maker Pro"


def test_accessibility_contrast_failure_blocks_publish(client, tenant, db_engine):
    page_id = _setup(client, tenant)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE page_templates
                SET schema = jsonb_set(
                    schema,
                    '{palette}',
                    '{"background": "#FFFFFF", "text": "#EEEEEE",
                      "cta_background": "#FFFFFF", "cta_text": "#EEEEEE"}'::jsonb
                )
                WHERE key = 'responsive'
                """
            )
        )

    blocked = _publish(client, tenant, page_id)

    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "publish_invalid"
    assert "contrast" in blocked.json()["error"]["message"]
