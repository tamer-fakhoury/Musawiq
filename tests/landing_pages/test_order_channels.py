"""FR-3.1.4: WhatsApp and COD ordering mechanisms."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from sqlalchemy import text


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


def _create(client, tenant):
    created = client.post(
        "/landing-pages/drafts", json=_payload(tenant), headers=_headers(tenant)
    )
    assert created.status_code == 201
    return created.json()["id"]


def test_whatsapp_channel_builds_wa_link_with_token(client, tenant):
    page_id = _create(client, tenant)

    response = client.put(
        f"/landing-pages/{page_id}/order-channel",
        json={
            "type": "whatsapp",
            "whatsapp_number": "+966 50 000 0000",
            "whatsapp_message_template": "أريد طلب هذا المنتج",
        },
        headers=_headers(tenant),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "whatsapp"
    assert body["whatsapp_number"] == "+966500000000"
    token = body["attribution_token"]
    assert token.startswith("lpt_")

    link = urlsplit(body["whatsapp_link"])
    assert link.scheme == "https"
    assert link.netloc == "wa.me"
    assert link.path == "/966500000000"
    text_value = parse_qs(link.query)["text"][0]
    assert "أريد طلب هذا المنتج" in text_value
    assert token in text_value

    page = client.get(f"/landing-pages/{page_id}", headers=_headers(tenant))
    assert page.json()["order_method"]["whatsapp_link"] == body["whatsapp_link"]
    assert page.json()["order_method"]["type"] == "whatsapp"


def test_cod_channel_requires_form_fields_and_verifies(client, tenant):
    page_id = _create(client, tenant)

    response = client.put(
        f"/landing-pages/{page_id}/order-channel",
        json={
            "type": "cod",
            "cod_form_schema": {
                "fields": [
                    {"name": "phone", "label": "الهاتف", "required": True},
                    {"name": "address", "label": "العنوان", "required": True},
                ]
            },
        },
        headers=_headers(tenant),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "cod"
    assert [field["name"] for field in body["cod_form_schema"]["fields"]] == [
        "phone",
        "address",
    ]

    verified = client.post(
        f"/landing-pages/{page_id}/order-channel/verify",
        headers=_headers(tenant),
    )
    assert verified.status_code == 200
    assert verified.json() == {"valid": True, "errors": []}


def test_invalid_channel_payloads_are_rejected(client, tenant):
    page_id = _create(client, tenant)

    bad_number = client.put(
        f"/landing-pages/{page_id}/order-channel",
        json={"type": "whatsapp", "whatsapp_number": "12"},
        headers=_headers(tenant),
    )
    assert bad_number.status_code == 422
    assert bad_number.json()["error"]["code"] == "invalid_whatsapp_number"

    bad_form = client.put(
        f"/landing-pages/{page_id}/order-channel",
        json={"type": "cod", "cod_form_schema": {"fields": []}},
        headers=_headers(tenant),
    )
    assert bad_form.status_code == 422
    assert bad_form.json()["error"]["code"] == "invalid_cod_schema"


def test_pre_publish_verification_reports_broken_form(
    client, tenant, db_engine
):
    page_id = _create(client, tenant)
    client.put(
        f"/landing-pages/{page_id}/order-channel",
        json={
            "type": "cod",
            "cod_form_schema": {
                "fields": [{"name": "phone", "required": True}]
            },
        },
        headers=_headers(tenant),
    )
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE order_channels SET cod_form_schema = "
                "'{\"schema_version\": 1, \"fields\": []}'::jsonb "
                "WHERE landing_page_id = :id"
            ),
            {"id": page_id},
        )

    checked = client.post(
        f"/landing-pages/{page_id}/order-channel/verify",
        headers=_headers(tenant),
    )
    assert checked.status_code == 200
    assert checked.json()["valid"] is False
    assert checked.json()["errors"]
