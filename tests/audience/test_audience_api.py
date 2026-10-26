"""Taxonomy read API and audience profile contracts."""

from __future__ import annotations

import uuid

from sqlalchemy import text


def _headers(tenant) -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": "owner",
    }


def _create_profile(client, tenant, niche_id: uuid.UUID, **extra):
    payload = {"niche_ids": [str(niche_id)], "languages": ["en"]}
    payload.update(extra)
    return client.post(
        "/audience-profiles", json=payload, headers=_headers(tenant)
    )


def test_categories_list_active_taxonomy_in_order(client, tenant, taxonomy):
    response = client.get("/categories", headers=_headers(tenant))

    assert response.status_code == 200
    items = response.json()
    assert [item["name"] for item in items] == ["Beauty", "Home", "Gadgets"]
    assert set(items[0]) == {
        "id",
        "parent_id",
        "name",
        "slug",
        "sort_order",
    }
    assert str(taxonomy.inactive) not in {item["id"] for item in items}
    child = next(item for item in items if item["id"] == str(taxonomy.child))
    assert child["parent_id"] == str(taxonomy.root)


def test_niches_include_global_and_caller_store_for_category(
    client, tenant, make_tenant, taxonomy, make_niche
):
    other = make_tenant()
    own_niche = make_niche(taxonomy.child, store_id=tenant.store_id, name="Own")
    other_niche = make_niche(
        taxonomy.child, store_id=other.store_id, name="Other Store"
    )

    response = client.get(
        "/niches",
        params={"category_id": str(taxonomy.child)},
        headers=_headers(tenant),
    )

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert ids == {str(taxonomy.global_niche), str(own_niche)}
    assert str(other_niche) not in ids


def test_create_profile_is_version_one_current_and_requires_niche(
    client, tenant, taxonomy
):
    created = _create_profile(
        client,
        tenant,
        taxonomy.global_niche,
        notes="Initial audience",
    )

    assert created.status_code == 201
    body = created.json()
    assert body["version"] == 1
    assert body["is_current"] is True
    assert body["status"] == "active"
    assert body["niche_ids"] == [str(taxonomy.global_niche)]
    assert body["languages"] == ["en"]
    assert body["notes"] == "Initial audience"
    assert body["created_by"] == str(tenant.user_id)

    current = client.get("/audience-profiles/current", headers=_headers(tenant))
    assert current.status_code == 200
    assert current.json()["id"] == body["id"]
    assert current.json()["segments"] == []

    missing_niche = client.post(
        "/audience-profiles",
        json={"niche_ids": [], "languages": ["en"]},
        headers=_headers(tenant),
    )
    assert missing_niche.status_code == 422


def test_update_creates_version_two_and_demotes_version_one(
    client, tenant, taxonomy, db_engine
):
    created = _create_profile(client, tenant, taxonomy.global_niche)
    profile_id = created.json()["id"]

    updated = client.patch(
        f"/audience-profiles/{profile_id}",
        json={"notes": "Revised", "languages": ["ar"]},
        headers=_headers(tenant),
    )

    assert updated.status_code == 200
    body = updated.json()
    assert body["version"] == 2
    assert body["is_current"] is True
    assert body["notes"] == "Revised"
    assert body["languages"] == ["ar"]
    assert body["niche_ids"] == [str(taxonomy.global_niche)]
    assert body["id"] != profile_id

    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT version, is_current FROM audience_profiles "
                "WHERE store_id = :store_id ORDER BY version"
            ),
            {"store_id": tenant.store_id},
        ).all()
    assert [(row.version, row.is_current) for row in rows] == [
        (1, False),
        (2, True),
    ]

    current = client.get("/audience-profiles/current", headers=_headers(tenant))
    assert current.json()["id"] == body["id"]


def test_segments_replaced_wholesale_and_invalid_age_rejected(
    client, tenant, taxonomy
):
    created = _create_profile(client, tenant, taxonomy.global_niche)
    profile_id = created.json()["id"]

    first = client.put(
        f"/audience-profiles/{profile_id}/segments",
        json={
            "segments": [
                {
                    "label": "Young",
                    "locations": ["SA"],
                    "age_min": 18,
                    "age_max": 30,
                    "interests": ["coffee"],
                },
                {
                    "label": "Older",
                    "locations": ["AE"],
                    "age_min": 31,
                    "age_max": 50,
                },
            ]
        },
        headers=_headers(tenant),
    )
    assert first.status_code == 200
    assert len(first.json()["segments"]) == 2

    current = client.get("/audience-profiles/current", headers=_headers(tenant))
    assert len(current.json()["segments"]) == 2

    replaced = client.put(
        f"/audience-profiles/{profile_id}/segments",
        json={
            "segments": [
                {
                    "label": "Only",
                    "locations": [],
                    "age_min": 25,
                    "age_max": 40,
                }
            ]
        },
        headers=_headers(tenant),
    )
    assert replaced.status_code == 200

    current = client.get("/audience-profiles/current", headers=_headers(tenant))
    assert [segment["label"] for segment in current.json()["segments"]] == [
        "Only"
    ]

    invalid = client.put(
        f"/audience-profiles/{profile_id}/segments",
        json={
            "segments": [
                {
                    "label": "Inverted",
                    "locations": [],
                    "age_min": 50,
                    "age_max": 40,
                }
            ]
        },
        headers=_headers(tenant),
    )
    assert invalid.status_code == 422

    current = client.get("/audience-profiles/current", headers=_headers(tenant))
    assert [segment["label"] for segment in current.json()["segments"]] == [
        "Only"
    ]


def test_other_store_cannot_see_or_change_profile(
    client, tenant, make_tenant, taxonomy
):
    other = make_tenant()
    created = _create_profile(client, tenant, taxonomy.global_niche)
    profile_id = created.json()["id"]

    current = client.get(
        "/audience-profiles/current", headers=_headers(other)
    )
    assert current.status_code == 404

    patched = client.patch(
        f"/audience-profiles/{profile_id}",
        json={"notes": "hijack"},
        headers=_headers(other),
    )
    assert patched.status_code == 404

    replaced = client.put(
        f"/audience-profiles/{profile_id}/segments",
        json={
            "segments": [
                {
                    "label": "hijack",
                    "locations": [],
                    "age_min": 18,
                    "age_max": 30,
                }
            ]
        },
        headers=_headers(other),
    )
    assert replaced.status_code == 404
