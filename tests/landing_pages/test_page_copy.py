"""FR-3.1.3: landing page copy generation, claims, and edits."""

from __future__ import annotations


class StubProvider:
    available = True
    model_version = "stub-v1"

    def __init__(self, payload: dict[str, str]) -> None:
        self.payload = payload

    def generate_json(self, system: str, user: str, schema: dict) -> dict:
        return dict(self.payload)


AR_COPY = {
    "headline": "آلة قهوة سهلة الاستخدام",
    "description": "قهوة طازجة في المنزل كل صباح",
    "cta_label": "اطلب عبر واتساب",
    "body": "حضّر قهوتك بخطوات بسيطة.",
}

EN_COPY = {
    "headline": "Easy home coffee",
    "description": "Fresh coffee every morning",
    "cta_label": "Order on WhatsApp",
    "body": "Brew your coffee in a few simple steps.",
}


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


def _create(client, tenant, **overrides):
    created = client.post(
        "/landing-pages/drafts",
        json=_payload(tenant, **overrides),
        headers=_headers(tenant),
    )
    assert created.status_code == 201
    return created.json()["id"]


def test_generates_rtl_arabic_copy_on_the_current_draft(client, tenant):
    page_id = _create(client, tenant)
    client.app.state.ai_provider = StubProvider(AR_COPY)

    response = client.post(
        f"/landing-pages/{page_id}/copy",
        json={},
        headers=_headers(tenant),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["headline"] == AR_COPY["headline"]
    assert body["language"] == "ar"
    assert body["direction"] == "rtl"
    assert body["generated_by"] == "ai"
    assert body["edited"] is False

    page = client.get(f"/landing-pages/{page_id}", headers=_headers(tenant))
    assert page.json()["draft_version"] == 1
    assert page.json()["direction"] == "rtl"
    assert page.json()["content"]["copy"]["headline"] == AR_COPY["headline"]


def test_generates_ltr_english_copy(client, tenant):
    page_id = _create(client, tenant, language="en", target_market="US")
    client.app.state.ai_provider = StubProvider(EN_COPY)

    response = client.post(
        f"/landing-pages/{page_id}/copy",
        json={},
        headers=_headers(tenant),
    )

    assert response.status_code == 200
    assert response.json()["direction"] == "ltr"
    assert response.json()["headline"] == EN_COPY["headline"]


def test_claim_filter_rejects_guaranteed_or_medical_copy(client, tenant):
    page_id = _create(client, tenant)

    for claim in ("نتائج مضمونة لكل عميل", "يعالج الصداع", "أفضل منتج في السوق"):
        client.app.state.ai_provider = StubProvider({**AR_COPY, "headline": claim})
        response = client.post(
            f"/landing-pages/{page_id}/copy",
            json={},
            headers=_headers(tenant),
        )
        assert response.status_code == 422, claim
        assert response.json()["error"]["code"] == "claim_rejected"

    page = client.get(f"/landing-pages/{page_id}", headers=_headers(tenant))
    assert "copy" not in page.json()["content"]


def test_edits_persist_and_block_regeneration_without_confirmation(client, tenant):
    page_id = _create(client, tenant)
    client.app.state.ai_provider = StubProvider(AR_COPY)
    client.post(f"/landing-pages/{page_id}/copy", json={}, headers=_headers(tenant))

    edited = client.put(
        f"/landing-pages/{page_id}/copy",
        json={"headline": "عنوان معدل يدويا"},
        headers=_headers(tenant),
    )
    assert edited.status_code == 200
    assert edited.json()["edited"] is True

    page = client.get(f"/landing-pages/{page_id}", headers=_headers(tenant))
    assert page.json()["content"]["copy"]["headline"] == "عنوان معدل يدويا"

    blocked = client.post(
        f"/landing-pages/{page_id}/copy",
        json={},
        headers=_headers(tenant),
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "manual_edits_exist"

    forced = client.post(
        f"/landing-pages/{page_id}/copy",
        json={"force": True},
        headers=_headers(tenant),
    )
    assert forced.status_code == 200
    assert forced.json()["edited"] is False
    assert forced.json()["headline"] == AR_COPY["headline"]
