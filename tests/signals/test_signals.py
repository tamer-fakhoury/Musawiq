"""Campaign signal ingestion and retrieval contracts."""

from __future__ import annotations

from sqlalchemy import text

START = "2026-01-01T00:00:00Z"
END = "2026-01-08T00:00:00Z"


def _headers(campaign) -> dict[str, str]:
    return {
        "X-Store-Id": str(campaign.store_id),
        "X-User-Id": str(campaign.user_id),
        "X-User-Role": "owner",
    }


def _body(**overrides):
    body = {
        "period_start": START,
        "period_end": END,
        "provider": "meta",
        "rows": [
            {
                "impressions": 1000,
                "reach": 800,
                "clicks": 50,
                "spend_minor": 10000,
                "conversions": 5,
                "engagement": 20,
            }
        ],
    }
    body.update(overrides)
    return body


def _count(db_engine, campaign) -> int:
    with db_engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT count(*) FROM metric_snapshots "
                "WHERE campaign_id = :campaign_id"
            ),
            {"campaign_id": campaign.campaign_id},
        ).scalar_one()


def test_happy_write_and_read_back(client, campaign, db_engine) -> None:
    response = client.post(
        f"/campaigns/{campaign.campaign_id}/signals",
        json=_body(),
        headers=_headers(campaign),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["campaign_id"] == str(campaign.campaign_id)
    assert body["rows_written"] == 1
    assert set(body["window"]) == {"start", "end"}

    listed = client.get(
        f"/campaigns/{campaign.campaign_id}/signals",
        headers=_headers(campaign),
    )

    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["impressions"] == 1000
    assert rows[0]["clicks"] == 50
    assert rows[0]["spend_minor"] == 10000
    assert rows[0]["ctr"] == 0.05
    assert rows[0]["cpc_minor"] == 200
    assert rows[0]["conversions"] == 5

    with db_engine.connect() as conn:
        snapshot = conn.execute(
            text(
                "SELECT test_id, provider, currency FROM metric_snapshots "
                "WHERE campaign_id = :campaign_id"
            ),
            {"campaign_id": campaign.campaign_id},
        ).mappings().one()

    assert snapshot["test_id"] == campaign.test_id
    assert snapshot["provider"] == "meta"
    assert snapshot["currency"] == "USD"


def test_repost_same_window_replaces(client, campaign, db_engine) -> None:
    first = client.post(
        f"/campaigns/{campaign.campaign_id}/signals",
        json=_body(),
        headers=_headers(campaign),
    )
    second = client.post(
        f"/campaigns/{campaign.campaign_id}/signals",
        json=_body(
            rows=[
                {
                    "impressions": 2000,
                    "reach": 1500,
                    "clicks": 100,
                    "spend_minor": 20000,
                    "conversions": 10,
                }
            ]
        ),
        headers=_headers(campaign),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["rows_written"] == 1
    assert _count(db_engine, campaign) == 1

    rows = client.get(
        f"/campaigns/{campaign.campaign_id}/signals",
        headers=_headers(campaign),
    ).json()
    assert rows[0]["impressions"] == 2000
    assert rows[0]["clicks"] == 100
    assert rows[0]["spend_minor"] == 20000
    assert rows[0]["ctr"] == 0.05
    assert rows[0]["cpc_minor"] == 200
    assert rows[0]["conversions"] == 10


def test_invalid_window_is_rejected(client, campaign, db_engine) -> None:
    response = client.post(
        f"/campaigns/{campaign.campaign_id}/signals",
        json=_body(period_end="2025-12-31T00:00:00Z"),
        headers=_headers(campaign),
    )

    assert response.status_code == 422
    assert _count(db_engine, campaign) == 0


def test_reach_above_impressions_is_rejected(
    client, campaign, db_engine
) -> None:
    response = client.post(
        f"/campaigns/{campaign.campaign_id}/signals",
        json=_body(
            rows=[
                {
                    "impressions": 1000,
                    "reach": 2000,
                    "clicks": 50,
                    "spend_minor": 10000,
                }
            ]
        ),
        headers=_headers(campaign),
    )

    assert response.status_code == 422
    assert _count(db_engine, campaign) == 0


def test_other_store_campaign_returns_404(
    client, campaign, make_campaign
) -> None:
    other = make_campaign()

    response = client.post(
        f"/campaigns/{campaign.campaign_id}/signals",
        json=_body(),
        headers=_headers(other),
    )

    assert response.status_code == 404
