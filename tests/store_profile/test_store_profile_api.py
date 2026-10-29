"""FR-1.2.1: store category and niche selection."""

from __future__ import annotations

from musawiq.services.store_profile import MAX_NICHE_NAME_LENGTH


def _headers(tenant) -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": "owner",
    }


def test_profile_saves_selected_categories_and_niches(
    client, tenant
) -> None:
    response = client.put(
        "/store/profile",
        json={
            "category_ids": [str(tenant.category_id)],
            "niche_ids": [str(tenant.niche_id)],
        },
        headers=_headers(tenant),
    )

    assert response.status_code == 200
    assert response.json() == {
        "category_ids": [str(tenant.category_id)],
        "niche_ids": [str(tenant.niche_id)],
    }

    saved = client.get("/store/profile", headers=_headers(tenant))
    assert saved.status_code == 200
    assert saved.json()["category_ids"] == [str(tenant.category_id)]


def test_profile_requires_at_least_one_category(client, tenant) -> None:
    response = client.put(
        "/store/profile",
        json={"category_ids": [], "niche_ids": []},
        headers=_headers(tenant),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "category_required"


def test_custom_niche_is_created_within_length_limit(client, tenant) -> None:
    response = client.post(
        "/niches",
        json={"category_id": str(tenant.category_id), "name": "Espresso Gear"},
        headers=_headers(tenant),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Espresso Gear"
    assert body["store_id"] == str(tenant.store_id)


def test_custom_niche_rejects_too_long_name(client, tenant) -> None:
    response = client.post(
        "/niches",
        json={
            "category_id": str(tenant.category_id),
            "name": "x" * (MAX_NICHE_NAME_LENGTH + 1),
        },
        headers=_headers(tenant),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "niche_name_too_long"
