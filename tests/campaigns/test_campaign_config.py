"""FR-3.2.3: campaign configuration and validation."""

from __future__ import annotations

import uuid

from sqlalchemy import text


def _headers(tenant) -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": "owner",
    }


def _campaign(tenant, **overrides):
    payload = {
        "test_id": str(tenant.test_id),
        "provider": "meta",
        "name": "Launch Campaign",
        "objective": "conversions",
        "budget_type": "daily",
        "budget_minor": 5000,
        "currency": "USD",
        "start_at": "2026-01-01T00:00:00Z",
        "end_at": "2026-01-31T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def _targeting(**overrides):
    targeting = {
        "schema_version": 1,
        "locations": ["SA"],
        "age_min": 18,
        "age_max": 40,
        "interests": ["coffee"],
    }
    targeting.update(overrides)
    return targeting


def _seed_audience(db_engine, tenant) -> uuid.UUID:
    profile_id = uuid.uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO audience_profiles (
                    id, store_id, version, status, is_current,
                    niche_ids, languages, created_by
                ) VALUES (
                    :id, :store_id, 1, 'active', true,
                    '{}', '{en}', :created_by
                )
                """
            ),
            {
                "id": profile_id,
                "store_id": tenant.store_id,
                "created_by": tenant.user_id,
            },
        )
    return profile_id


def test_campaign_and_adset_are_saved_as_drafts_with_saved_audience(
    client, tenant, db_engine
):
    profile_id = _seed_audience(db_engine, tenant)

    created = client.post(
        "/campaigns", json=_campaign(tenant), headers=_headers(tenant)
    )
    assert created.status_code == 201
    campaign = created.json()
    assert campaign["status"] == "draft"
    assert campaign["provider"] == "meta"
    assert campaign["budget_minor"] == 5000
    assert campaign["currency"] == "USD"

    adset = client.post(
        f"/campaigns/{campaign['id']}/adsets",
        json={
            "name": "Saudi coffee lovers",
            "targeting": _targeting(audience_profile_id=str(profile_id)),
        },
        headers=_headers(tenant),
    )
    assert adset.status_code == 201
    body = adset.json()
    assert body["status"] == "draft"
    assert body["targeting"]["schema_version"] == 1
    assert body["targeting"]["audience_profile_id"] == str(profile_id)
    assert body["targeting"]["locations"] == ["SA"]
    assert body["targeting"]["age_min"] == 18
    assert body["targeting"]["interests"] == ["coffee"]


def test_campaign_requires_valid_dates_and_platform_minimum_budget(
    client, tenant
):
    too_cheap = client.post(
        "/campaigns",
        json=_campaign(tenant, budget_minor=100),
        headers=_headers(tenant),
    )
    assert too_cheap.status_code == 422

    bad_dates = client.post(
        "/campaigns",
        json=_campaign(
            tenant,
            start_at="2026-02-01T00:00:00Z",
            end_at="2026-01-01T00:00:00Z",
        ),
        headers=_headers(tenant),
    )
    assert bad_dates.status_code == 422

    unknown_platform = client.post(
        "/campaigns",
        json=_campaign(tenant, provider="myspace"),
        headers=_headers(tenant),
    )
    assert unknown_platform.status_code == 422

    missing_name = client.post(
        "/campaigns",
        json=_campaign(tenant, name=""),
        headers=_headers(tenant),
    )
    assert missing_name.status_code == 422


def test_targeting_requires_schema_and_valid_locations_and_ages(
    client, tenant
):
    campaign = client.post(
        "/campaigns", json=_campaign(tenant), headers=_headers(tenant)
    ).json()
    url = f"/campaigns/{campaign['id']}/adsets"

    missing_schema = client.post(
        url,
        json={
            "name": "No schema",
            "targeting": {"locations": ["SA"], "age_min": 18, "age_max": 30},
        },
        headers=_headers(tenant),
    )
    assert missing_schema.status_code == 422

    bad_location = client.post(
        url,
        json={"name": "Bad place", "targeting": _targeting(locations=["ZZ"])},
        headers=_headers(tenant),
    )
    assert bad_location.status_code == 422

    bad_age = client.post(
        url,
        json={
            "name": "Too old",
            "targeting": _targeting(age_min=18, age_max=200),
        },
        headers=_headers(tenant),
    )
    assert bad_age.status_code == 422
