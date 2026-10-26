"""Re-analysis parent linking and delta behaviour."""

from __future__ import annotations

from musawiq.ai.providers import FixtureProvider


def _headers(seed) -> dict[str, str]:
    return {
        "X-Store-Id": str(seed.store_id),
        "X-User-Id": str(seed.user_id),
        "X-User-Role": "owner",
    }


def _create(client, seed, *, campaign_id=None, body=None) -> dict:
    client.app.state.ai_provider = FixtureProvider()
    response = client.post(
        f"/campaigns/{campaign_id or seed.campaign_id}/analyses",
        headers=_headers(seed),
        json=body or {},
    )
    assert response.status_code == 201
    return response.json()


def test_parent_link_is_persisted(client, seed) -> None:
    parent = _create(client, seed)
    child = _create(
        client,
        seed,
        body={"parent_analysis_id": parent["id"]},
    )

    assert child["parent_analysis_id"] == parent["id"]

    detail = client.get(
        f"/analyses/{child['id']}", headers=_headers(seed)
    )
    assert detail.status_code == 200
    assert detail.json()["parent_analysis_id"] == parent["id"]


def test_delta_is_present_and_non_empty(client, seed) -> None:
    parent = _create(client, seed)
    child = _create(
        client,
        seed,
        body={"parent_analysis_id": parent["id"]},
    )

    delta = child["result"]["delta"]
    assert delta is not None
    assert delta["metrics"]
    assert any(row["metric"] == "ctr" for row in delta["metrics"])
    assert delta["summary"]["headline"] in {
        "improved",
        "degraded",
        "flat",
        "mixed",
    }


def test_parent_from_another_campaign_is_rejected(client, seed) -> None:
    parent = _create(client, seed)

    response = client.post(
        f"/campaigns/{seed.other_campaign_id}/analyses",
        headers=_headers(seed),
        json={"parent_analysis_id": parent["id"]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_analysis"


def test_without_parent_delta_is_null(client, seed) -> None:
    body = _create(client, seed)

    assert body["parent_analysis_id"] is None
    assert body["result"]["delta"] is None
