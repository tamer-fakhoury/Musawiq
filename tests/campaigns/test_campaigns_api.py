"""Campaign setup, manual edits, and configuration fingerprint."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext, set_local_tenant
from musawiq.services.campaigns import config_fingerprint

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = START + timedelta(days=7)


def _headers(tenant) -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": "owner",
    }


def _create_campaign(client, tenant, **overrides):
    payload = {
        "test_id": str(tenant.test_id),
        "provider": "meta",
        "name": "Ramadan campaign",
        "objective": "conversions",
        "budget_type": "daily",
        "budget_minor": 5000,
        "currency": "USD",
        "start_at": START.isoformat(),
        "end_at": END.isoformat(),
    }
    payload.update(overrides)
    return client.post("/campaigns", json=payload, headers=_headers(tenant))


def _create_adset(client, tenant, campaign_id: str, **overrides):
    payload = {
        "name": "Saudi audience",
        "targeting": {
            "locations": ["SA"],
            "age_min": 18,
            "age_max": 35,
            "genders": ["all"],
            "interests": ["coffee"],
            "languages": ["ar"],
        },
    }
    payload.update(overrides)
    return client.post(
        f"/campaigns/{campaign_id}/adsets",
        json=payload,
        headers=_headers(tenant),
    )


def _create_variation(client, tenant, campaign_id: str, adset_id: str, **extra):
    payload = {
        "adset_id": adset_id,
        "copy_text": "قهوة مختصة تصلك حتى بابك",
        "headline": "عرض اليوم",
        "description": "اطلب الآن",
        "destination_url": "https://example.test/offer",
    }
    payload.update(extra)
    return client.post(
        f"/campaigns/{campaign_id}/variations",
        json=payload,
        headers=_headers(tenant),
    )


def _fingerprint(db_engine, tenant, campaign_id: str) -> str:
    with Session(db_engine) as session:
        session.begin()
        set_local_tenant(session, tenant.store_id, tenant.user_id)
        try:
            return config_fingerprint(
                session,
                TenantContext(
                    store_id=tenant.store_id,
                    user_id=tenant.user_id,
                    role="owner",
                ),
                campaign_id,
            )
        finally:
            session.rollback()


def test_create_and_fetch_campaign_with_nested_assets(client, tenant):
    created = _create_campaign(client, tenant)
    assert created.status_code == 201
    campaign = created.json()
    assert campaign["status"] == "draft"
    assert campaign["provider"] == "meta"
    assert campaign["created_by"] == str(tenant.user_id)
    assert campaign["test_id"] == str(tenant.test_id)

    adset = _create_adset(client, tenant, campaign["id"])
    assert adset.status_code == 201
    adset_body = adset.json()
    assert adset_body["campaign_id"] == campaign["id"]
    assert adset_body["targeting"]["age_max"] == 35

    variation = _create_variation(
        client, tenant, campaign["id"], adset_body["id"]
    )
    assert variation.status_code == 201
    variation_body = variation.json()
    assert variation_body["status"] == "draft"
    assert variation_body["adset_id"] == adset_body["id"]

    detail = client.get(
        f"/campaigns/{campaign['id']}", headers=_headers(tenant)
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == campaign["id"]
    assert len(body["ad_sets"]) == 1
    assert body["ad_sets"][0]["id"] == adset_body["id"]
    assert len(body["ad_sets"][0]["variations"]) == 1
    assert body["ad_sets"][0]["variations"][0]["copy_text"] == (
        "قهوة مختصة تصلك حتى بابك"
    )

    listed = client.get("/campaigns", headers=_headers(tenant))
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [campaign["id"]]

    patched = client.patch(
        f"/campaigns/{campaign['id']}",
        json={
            "name": "Ramadan campaign v2",
            "budget_minor": 7500,
            "status": "active",
        },
        headers=_headers(tenant),
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Ramadan campaign v2"
    assert patched.json()["budget_minor"] == 7500
    assert patched.json()["status"] == "active"

    paused = client.patch(
        f"/campaigns/{campaign['id']}",
        json={"status": "paused"},
        headers=_headers(tenant),
    )
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    edited = client.patch(
        f"/ad-variations/{variation_body['id']}",
        json={
            "copy_text": "قهوة مختصة بخصم خاص",
            "headline": "خصم 20%",
            "status": "approved",
        },
        headers=_headers(tenant),
    )
    assert edited.status_code == 200
    assert edited.json()["copy_text"] == "قهوة مختصة بخصم خاص"
    assert edited.json()["status"] == "approved"


def test_invalid_dates_are_rejected(client, tenant):
    response = _create_campaign(
        client,
        tenant,
        end_at=START.isoformat(),
    )

    assert response.status_code == 422


def test_variation_without_destination_is_rejected(client, tenant):
    campaign = _create_campaign(client, tenant).json()
    adset = _create_adset(client, tenant, campaign["id"]).json()

    response = _create_variation(
        client,
        tenant,
        campaign["id"],
        adset["id"],
        destination_url=None,
    )

    assert response.status_code == 422


def test_other_store_cannot_read_or_change_campaign(
    client, tenant, make_tenant
):
    other = make_tenant()
    campaign = _create_campaign(client, tenant).json()
    adset = _create_adset(client, tenant, campaign["id"]).json()

    detail = client.get(
        f"/campaigns/{campaign['id']}", headers=_headers(other)
    )
    assert detail.status_code == 404

    patched = client.patch(
        f"/campaigns/{campaign['id']}",
        json={"name": "hijack"},
        headers=_headers(other),
    )
    assert patched.status_code == 404

    adset_attempt = client.post(
        f"/campaigns/{campaign['id']}/adsets",
        json={"name": "hijack", "targeting": {}},
        headers=_headers(other),
    )
    assert adset_attempt.status_code == 404

    variation = _create_variation(
        client, tenant, campaign["id"], adset["id"]
    ).json()
    variation_attempt = client.patch(
        f"/ad-variations/{variation['id']}",
        json={"copy_text": "hijack"},
        headers=_headers(other),
    )
    assert variation_attempt.status_code == 404


def test_fingerprint_changes_when_copy_changes(client, tenant, db_engine):
    campaign = _create_campaign(client, tenant).json()
    adset = _create_adset(client, tenant, campaign["id"]).json()
    variation = _create_variation(
        client, tenant, campaign["id"], adset["id"]
    ).json()

    before = _fingerprint(db_engine, tenant, campaign["id"])
    again = _fingerprint(db_engine, tenant, campaign["id"])
    assert before == again
    assert len(before) == 64

    response = client.patch(
        f"/ad-variations/{variation['id']}",
        json={"copy_text": "نص إعلاني جديد تماما"},
        headers=_headers(tenant),
    )
    assert response.status_code == 200

    after = _fingerprint(db_engine, tenant, campaign["id"])
    assert after != before
