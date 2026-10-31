"""FR-5.2.6: assumption overrides, versioned recalculation, history/diff."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import text

PROFILE = {
    "unit_cost_minor": 2000,
    "selling_price_minor": 5000,
    "fulfillment_cost_minor": 500,
    "payment_fee_bp": 300,
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


def _snapshot(db_engine, site):
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=7)
    with db_engine.begin() as conn:
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
                    40000, 5000, 1000, 50, 0, 0.05, 800, 1.0, '{}', now()
                )
                """
            ),
            {
                "store_id": site.store_id,
                "test_id": site.test_id,
                "start": start,
                "end": end,
            },
        )


def _recalculate(client, site, payload):
    return client.post(
        f"/tests/{site.test_id}/recommendations/recalculate",
        json=payload,
        headers=_headers(site),
    )


def test_recalculation_versions_recommendation_with_fresh_outputs(
    client, site, db_engine
):
    _snapshot(db_engine, site)

    first = _recalculate(
        client,
        site,
        {"profile": PROFILE, "assumptions": {"repeat_rate": 0.1}},
    )
    assert first.status_code == 201, first.text
    v1 = first.json()
    assert v1["version"] == 1
    assert v1["is_current"] is True
    assert v1["demand_estimate"]["low_units"] <= v1["demand_estimate"]["high_units"]
    assert v1["unit_economics"]["contribution_margin_minor"] == 2350
    assert [row["label"] for row in v1["quantity_scenarios"]] == [
        "conservative",
        "base",
        "aggressive",
    ]

    second = _recalculate(
        client,
        site,
        {
            "profile": {**PROFILE, "selling_price_minor": 6000},
            "assumptions": {"repeat_rate": 0.3},
        },
    )
    assert second.status_code == 201
    v2 = second.json()
    assert v2["version"] == 2
    assert v2["is_current"] is True

    changed = {entry["field"]: entry for entry in v2["changes"]["changed"]}
    assert changed["repeat_rate"] == {
        "field": "repeat_rate",
        "before": 0.1,
        "after": 0.3,
    }
    assert changed["selling_price_minor"]["before"] == 5000
    assert changed["selling_price_minor"]["after"] == 6000

    history = client.get(
        f"/tests/{site.test_id}/recommendations", headers=_headers(site)
    ).json()
    assert [row["version"] for row in history] == [2, 1]
    assert [row["is_current"] for row in history] == [True, False]

    current = client.get(
        f"/tests/{site.test_id}/recommendations/current",
        headers=_headers(site),
    ).json()
    assert current["id"] == v2["id"]

    with db_engine.connect() as conn:
        v1_demands = conn.execute(
            text(
                "SELECT count(*) FROM demand_estimates "
                "WHERE investment_recommendation_id = :id"
            ),
            {"id": v1["id"]},
        ).scalar_one()
        v1_scenarios = conn.execute(
            text(
                "SELECT count(*) FROM quantity_scenarios "
                "WHERE investment_recommendation_id = :id"
            ),
            {"id": v1["id"]},
        ).scalar_one()
        v2_scenarios = conn.execute(
            text(
                "SELECT count(*) FROM quantity_scenarios "
                "WHERE investment_recommendation_id = :id"
            ),
            {"id": v2["id"]},
        ).scalar_one()
    assert v1_demands == 1
    assert v1_scenarios == 3
    assert v2_scenarios == 3


def test_recalculation_requires_snapshot_and_valid_assumptions(client, site):
    missing = _recalculate(client, site, {"profile": PROFILE})
    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "no_snapshot"


def test_invalid_assumption_value_is_rejected(client, site, db_engine):
    _snapshot(db_engine, site)

    response = _recalculate(
        client,
        site,
        {"profile": PROFILE, "assumptions": {"repeat_rate": 2}},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_assumption"
