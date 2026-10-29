"""FR-3.1.1: product input and landing page draft options."""

from __future__ import annotations

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


def _upload_image(client, tenant, *, name="product.png", content=PNG_BYTES,
                  content_type="image/png"):
    return client.post(
        "/landing-pages/images",
        files={"file": (name, content, content_type)},
        headers=_headers(tenant),
    )


def test_draft_captures_product_fields_image_and_order_method(client, tenant):
    uploaded = _upload_image(client, tenant)
    assert uploaded.status_code == 201
    image_id = uploaded.json()["id"]

    response = client.post(
        "/landing-pages/drafts",
        json=_payload(tenant, image_file_ids=[image_id]),
        headers=_headers(tenant),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["language"] == "ar"
    assert body["currency"] == "USD"
    assert body["price_minor"] == 4999
    assert body["image_file_ids"] == [image_id]
    assert body["content"] == {
        "schema_version": 1,
        "name": "Coffee Maker",
        "description": "Compact espresso machine",
        "target_market": "SA",
    }
    assert body["order_method"] == {
        "type": "whatsapp",
        "whatsapp_number": "+966500000000",
        "whatsapp_message_template": None,
        "cod_form_schema": None,
    }


def test_image_type_is_limited(client, tenant):
    response = _upload_image(
        client, tenant, name="product.gif", content=b"GIF89a", content_type="image/gif"
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_image_type"


def test_mandatory_fields_are_validated(client, tenant):
    missing_name = client.post(
        "/landing-pages/drafts",
        json=_payload(tenant, name=""),
        headers=_headers(tenant),
    )
    assert missing_name.status_code == 422
    assert missing_name.json()["error"]["code"] == "invalid_name"

    bad_market = client.post(
        "/landing-pages/drafts",
        json=_payload(tenant, target_market="ZZ"),
        headers=_headers(tenant),
    )
    assert bad_market.status_code == 422
    assert bad_market.json()["error"]["code"] == "invalid_target_market"


def test_autosave_creates_a_new_version_per_save(client, tenant, db_engine):
    created = client.post(
        "/landing-pages/drafts", json=_payload(tenant), headers=_headers(tenant)
    )
    page_id = created.json()["id"]
    assert created.json()["draft_version"] == 1

    saved = client.put(
        f"/landing-pages/{page_id}/draft",
        json=_payload(tenant, name="Coffee Maker v2"),
        headers=_headers(tenant),
    )
    assert saved.status_code == 200
    assert saved.json()["draft_version"] == 2
    assert saved.json()["content"]["name"] == "Coffee Maker v2"

    from sqlalchemy import text

    with db_engine.connect() as conn:
        versions = conn.execute(
            text(
                "SELECT version FROM page_versions "
                "WHERE landing_page_id = :id ORDER BY version"
            ),
            {"id": page_id},
        ).scalars().all()
    assert versions == [1, 2]


def test_order_method_is_whatsapp_or_cod(client, tenant):
    cod = client.post(
        "/landing-pages/drafts",
        json=_payload(
            tenant,
            order_method={"type": "cod", "cod_form_schema": {"fields": ["phone"]}},
        ),
        headers=_headers(tenant),
    )
    assert cod.status_code == 201
    assert cod.json()["order_method"]["type"] == "cod"

    missing_number = client.post(
        "/landing-pages/drafts",
        json=_payload(tenant, order_method={"type": "whatsapp"}),
        headers=_headers(tenant),
    )
    assert missing_number.status_code == 422
    assert missing_number.json()["error"]["code"] == "invalid_order_method"
