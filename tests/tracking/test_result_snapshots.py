"""FR-5.1.1: immutable test result snapshots."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def _headers(site):
    return {
        "X-Store-Id": str(site.store_id),
        "X-User-Id": str(site.user_id),
        "X-User-Role": "owner",
    }


def _window():
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=2)
    return start.isoformat(), end.isoformat()


def _metric(db_engine, site, start, end, *, spend, impressions, clicks):
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO metric_snapshots (
                    store_id, test_id, provider, campaign_id, period_start,
                    period_end, snapshot_at, currency, spend_minor,
                    impressions, reach, clicks
                ) VALUES (
                    :store_id, :test_id, 'meta', :campaign_id, :start, :end,
                    now(), 'USD', :spend, :impressions, :impressions, :clicks
                )
                """
            ),
            {
                "store_id": site.store_id,
                "test_id": site.test_id,
                "campaign_id": site.campaign_id,
                "start": start,
                "end": end,
                "spend": spend,
                "impressions": impressions,
                "clicks": clicks,
            },
        )


def _event(db_engine, site, event_type, occurred_at):
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO events (
                    store_id, event_id, test_id, campaign_id, event_type,
                    source, occurred_at, is_bot, properties
                ) VALUES (
                    :store_id, :event_id, :test_id, :campaign_id, :event_type,
                    'server', :occurred_at, false,
                    '{"schema_version": 1}'::jsonb
                )
                """
            ),
            {
                "store_id": site.store_id,
                "event_id": uuid.uuid4(),
                "test_id": site.test_id,
                "campaign_id": site.campaign_id,
                "event_type": event_type,
                "occurred_at": occurred_at,
            },
        )


def _snapshot(client, site, start, end):
    return client.post(
        f"/tests/{site.test_id}/result-snapshots",
        json={"period_start": start, "period_end": end},
        headers=_headers(site),
    )


def test_snapshot_aggregates_metrics_and_primary_conversions(
    client, site, db_engine
):
    start, end = _window()
    start_dt = dt.datetime.fromisoformat(start)
    end_dt = dt.datetime.fromisoformat(end)
    midpoint = start_dt + (end_dt - start_dt) / 2
    _metric(
        db_engine, site, start_dt, midpoint,
        spend=1000, impressions=100, clicks=10,
    )
    _metric(
        db_engine, site, midpoint, end_dt,
        spend=2000, impressions=200, clicks=20,
    )
    for _ in range(3):
        _event(db_engine, site, "cod_order_submitted", midpoint)

    response = _snapshot(client, site, start, end)

    assert response.status_code == 201
    body = response.json()
    assert body["spend_minor"] == 3000
    assert body["impressions"] == 300
    assert body["clicks"] == 30
    assert body["tracked_conversions"] == 3
    assert body["conversion_rate"] == 0.1
    assert body["cost_per_conversion_minor"] == 1000
    assert body["data_completeness"] == 1.0
    assert body["warnings"] == []
    assert body["currency"] == "USD"
    assert len(body["source_metric_snapshot_ids"]) == 2


def test_missing_data_is_identified_not_silently_zeroed(client, site):
    start, end = _window()

    response = _snapshot(client, site, start, end)

    assert response.status_code == 201
    body = response.json()
    assert body["spend_minor"] == 0
    assert body["clicks"] == 0
    assert body["tracked_conversions"] == 0
    assert body["data_completeness"] < 1.0
    assert "metric_snapshots_missing" in body["warnings"]
    assert "conversion_events_missing" in body["warnings"]


def test_confirmed_deposits_count_and_snapshot_is_immutable(
    client, site, db_engine
):
    now = dt.datetime.now(dt.timezone.utc)
    start = (now - dt.timedelta(days=1)).isoformat()
    end = (now + dt.timedelta(hours=1)).isoformat()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE tests SET primary_conversion = 'deposit_confirmed' "
                "WHERE id = :id"
            ),
            {"id": site.test_id},
        )
        order_id = conn.execute(
            text(
                """
                INSERT INTO orders (
                    store_id, origin, test_id, test_phase, status, currency,
                    total_minor, placed_at
                ) VALUES (
                    :store_id, 'cod', :test_id, 'during_test', 'pending',
                    'USD', 5000, now()
                )
                RETURNING id
                """
            ),
            {"store_id": site.store_id, "test_id": site.test_id},
        ).scalar_one()
        conn.execute(
            text(
                """
                INSERT INTO deposits (
                    store_id, order_id, test_id, status, amount_minor,
                    currency, method, verified_by, verified_at
                ) VALUES (
                    :store_id, :order_id, :test_id, 'confirmed', 5000,
                    'USD', 'manual', :user_id, now()
                )
                """
            ),
            {
                "store_id": site.store_id,
                "order_id": order_id,
                "test_id": site.test_id,
                "user_id": site.user_id,
            },
        )
    _event(db_engine, site, "deposit_confirmed", now)

    response = _snapshot(client, site, start, end)
    assert response.status_code == 201
    body = response.json()
    assert body["confirmed_deposits"] == 1
    assert body["tracked_conversions"] == 1

    with pytest.raises(DBAPIError):
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE test_result_snapshots SET clicks = 999 "
                    "WHERE id = :id"
                ),
                {"id": body["id"]},
            )
