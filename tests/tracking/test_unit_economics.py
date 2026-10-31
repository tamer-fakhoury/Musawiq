"""FR-5.2.3: unit economics and CAC."""

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


def _snapshot(db_engine, site, *, spend=40000, conversions=50):
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=7)
    with db_engine.begin() as conn:
        return conn.execute(
            text(
                """
                INSERT INTO test_result_snapshots (
                    store_id, test_id, period_start, period_end, currency,
                    spend_minor, impressions, clicks, tracked_conversions,
                    confirmed_deposits, conversion_rate,
                    cost_per_conversion_minor, data_completeness,
                    source_metric_snapshot_ids, captured_at
                ) VALUES (
                    :store_id, :test_id, :start, :end, 'USD', :spend,
                    5000, 1000, :conversions, 0, 0.05, 800, 1.0, '{}', now()
                )
                RETURNING id
                """
            ),
            {
                "store_id": site.store_id,
                "test_id": site.test_id,
                "start": start,
                "end": end,
                "spend": spend,
                "conversions": conversions,
            },
        ).scalar_one()


def _calculate(client, site, payload):
    return client.post(
        f"/tests/{site.test_id}/unit-economics",
        json=payload,
        headers=_headers(site),
    )


def test_positive_margin_economics_and_formulas(client, site, db_engine):
    _snapshot(db_engine, site)

    response = _calculate(client, site, {"profile": PROFILE})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["contribution_margin_minor"] == 2350
    assert body["break_even_units"] == 85.11
    assert body["cac_minor"] == 800
    assert body["is_negative_margin"] is False
    assert body["warnings"] == []
    formulas = body["formulas"]
    assert formulas["schema_version"] == 1
    assert "5000 - 2000 - 500" in formulas["contribution_margin_minor"]
    assert "200000 / 2350" in formulas["break_even_units"]
    assert "40000 / 50" in formulas["cac_minor"]


def test_negative_margin_is_flagged_without_break_even(client, site, db_engine):
    _snapshot(db_engine, site)
    expensive = {**PROFILE, "unit_cost_minor": 6000}

    response = _calculate(client, site, {"profile": expensive})

    assert response.status_code == 201
    body = response.json()
    assert body["contribution_margin_minor"] < 0
    assert body["is_negative_margin"] is True
    assert body["break_even_units"] is None
    assert body["warnings"]
    assert "NEGATIVE MARGIN" in body["warnings"][0]


def test_economics_requires_snapshot(client, site):
    response = _calculate(client, site, {"profile": PROFILE})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_snapshot"
