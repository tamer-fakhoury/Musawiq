"""FR-5.2.2: demand estimation with explicit assumptions."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import text

PROFILE = {
    "unit_cost_minor": 2000,
    "selling_price_minor": 5000,
    "available_budget_minor": 200000,
    "target_margin_bp": 4000,
    "supplier_moq": 100,
    "lead_time_days": 14,
    "currency": "USD",
}


def _headers(site):
    return {
        "X-Store-Id": str(site.store_id),
        "X-User-Id": str(site.user_id),
        "X-User-Role": "owner",
    }


def _snapshot(db_engine, site, *, clicks=2000, conversions=50, completeness=1.0):
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=7)
    with db_engine.begin() as conn:
        return str(
            conn.execute(
                text(
                    """
                    INSERT INTO test_result_snapshots (
                        store_id, test_id, period_start, period_end, currency,
                        spend_minor, impressions, clicks, tracked_conversions,
                        confirmed_deposits, conversion_rate,
                        cost_per_conversion_minor, data_completeness,
                        source_metric_snapshot_ids, captured_at
                    ) VALUES (
                        :store_id, :test_id, :start, :end, 'USD',
                        40000, :impressions, :clicks, :conversions,
                        0, :rate, 800, :completeness, '{}', now()
                    )
                    RETURNING id
                    """
                ),
                {
                    "store_id": site.store_id,
                    "test_id": site.test_id,
                    "start": start,
                    "end": end,
                    "impressions": clicks * 10,
                    "clicks": clicks,
                    "conversions": conversions,
                    "rate": round(conversions / clicks, 6) if clicks else None,
                    "completeness": completeness,
                },
            ).scalar_one()
        )


def _estimate(client, site, payload):
    return client.post(
        f"/tests/{site.test_id}/demand-estimates",
        json=payload,
        headers=_headers(site),
    )


def test_estimate_is_a_range_with_explicit_assumptions(client, site, db_engine):
    _snapshot(db_engine, site)

    response = _estimate(
        client,
        site,
        {
            "profile": PROFILE,
            "assumptions": {
                "repeat_rate": 0.2,
                "seasonality_factor": 1.1,
                "attribution_adjustment": 0.8,
                "traffic_source": "meta_ads",
            },
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["low_units"] == 37
    assert body["base_units"] == 53
    assert body["high_units"] == 69
    assert body["low_units"] <= body["base_units"] <= body["high_units"]
    assert body["confidence"] == "high"
    assert body["investment_recommendation_id"]
    assert body["limitations"]

    assumptions = body["assumptions"]
    assert assumptions["schema_version"] == 1
    for key in (
        "traffic_source",
        "repeat_rate",
        "seasonality_factor",
        "attribution_adjustment",
    ):
        assert {"value", "source"} <= set(assumptions[key])
    assert assumptions["traffic_source"]["value"] == "meta_ads"
    assert assumptions["repeat_rate"]["value"] == 0.2
    assert assumptions["seasonality_factor"]["value"] == 1.1
    assert assumptions["attribution_adjustment"]["value"] == 0.8


def test_partial_or_small_samples_lower_confidence(client, site, db_engine):
    _snapshot(db_engine, site, clicks=50, conversions=2, completeness=0.6)

    response = _estimate(client, site, {"profile": PROFILE})

    assert response.status_code == 201
    body = response.json()
    assert body["confidence"] == "low"
    limitations = " ".join(body["limitations"])
    assert "partial" in limitations
    assert "sample size" in limitations
    assert body["low_units"] <= body["base_units"] <= body["high_units"]


def test_estimate_requires_snapshot_and_profile(client, site, db_engine):
    missing_snapshot = _estimate(client, site, {"profile": PROFILE})
    assert missing_snapshot.status_code == 409
    assert missing_snapshot.json()["error"]["code"] == "no_snapshot"

    _snapshot(db_engine, site)
    missing_profile = _estimate(client, site, {})
    assert missing_profile.status_code == 409
    assert missing_profile.json()["error"]["code"] == "profile_required"
