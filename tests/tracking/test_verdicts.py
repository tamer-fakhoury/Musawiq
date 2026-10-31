"""FR-5.1.4: deterministic verdict classification."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import text


def _headers(site):
    return {
        "X-Store-Id": str(site.store_id),
        "X-User-Id": str(site.user_id),
        "X-User-Role": "owner",
    }


def _rule(client, site, **overrides):
    payload = {
        "min_spend_minor": 10000,
        "min_clicks": 100,
        "min_conversions": 5,
        "min_confirmed_deposits": 0,
        "min_conversion_rate": 0.02,
        "max_cost_per_conversion_minor": 2000,
        "rules": {"schema_version": 1},
    }
    payload.update(overrides)
    response = client.post(
        "/decision-rule-sets", json=payload, headers=_headers(site)
    )
    assert response.status_code == 201, response.text
    return response.json()


def _snapshot(db_engine, site, **overrides):
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=2)
    values = {
        "spend_minor": 20000,
        "impressions": 1000,
        "clicks": 500,
        "tracked_conversions": 20,
        "confirmed_deposits": 5,
        "conversion_rate": 0.04,
        "cost_per_conversion_minor": 1000,
        "data_completeness": 1.0,
    }
    values.update(overrides)
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
                        :spend_minor, :impressions, :clicks,
                        :tracked_conversions, :confirmed_deposits,
                        :conversion_rate, :cost_per_conversion_minor,
                        :data_completeness, '{}', now()
                    )
                    RETURNING id
                    """
                ),
                {
                    "store_id": site.store_id,
                    "test_id": site.test_id,
                    "start": start,
                    "end": end,
                    **values,
                },
            ).scalar_one()
        )


def _evaluate(client, site):
    return client.post(f"/tests/{site.test_id}/verdicts", headers=_headers(site))


def _status(db_engine, site):
    with db_engine.connect() as conn:
        return conn.execute(
            text("SELECT status FROM tests WHERE id = :id"),
            {"id": site.test_id},
        ).scalar_one()


def test_go_verdict_is_deterministic_and_completes_test(
    client, site, db_engine
):
    rule = _rule(client, site)
    snapshot_id = _snapshot(db_engine, site)

    first = _evaluate(client, site)
    second = _evaluate(client, site)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["outcome"] == "go"
    assert second.json()["outcome"] == "go"
    assert first.json()["is_conclusive"] is True
    assert first.json()["result_snapshot_id"] == snapshot_id
    assert first.json()["decision_rule_set_id"] == rule["id"]
    assert first.json()["rule_set_version"] == rule["version"]
    assert first.json()["rule_trace"] == second.json()["rule_trace"]
    assert first.json()["created_at"]
    assert _status(db_engine, site) == "completed"

    checks = first.json()["rule_trace"]["checks"]
    assert {check["rule"] for check in checks} >= {
        "data_completeness",
        "min_conversion_rate",
        "max_cost_per_conversion_minor",
    }
    assert all(
        {"rule", "threshold", "observed", "passed"} <= set(check)
        for check in checks
    )


def test_sufficiency_gate_forces_extend_test(client, site, db_engine):
    _rule(client, site)
    _snapshot(db_engine, site, data_completeness=0.5)

    response = _evaluate(client, site)

    assert response.status_code == 201
    body = response.json()
    assert body["outcome"] == "extend_test"
    assert body["is_conclusive"] is False
    assert body["limitations"]
    assert _status(db_engine, site) == "extended"


def test_failed_performance_thresholds_are_no_go(client, site, db_engine):
    _rule(client, site)
    _snapshot(
        db_engine,
        site,
        conversion_rate=0.01,
        cost_per_conversion_minor=3000,
    )

    response = _evaluate(client, site)

    assert response.status_code == 201
    body = response.json()
    assert body["outcome"] == "no_go"
    assert body["is_conclusive"] is True
    failing = {
        check["rule"]
        for check in body["rule_trace"]["checks"]
        if not check["passed"]
    }
    assert {"min_conversion_rate", "max_cost_per_conversion_minor"} <= failing
    assert _status(db_engine, site) == "completed"


def test_evaluation_requires_snapshot_and_rule_set(client, site, db_engine):
    no_rule = _evaluate(client, site)
    assert no_rule.status_code == 409
    assert no_rule.json()["error"]["code"] == "no_snapshot"

    _rule(client, site)
    still_missing = _evaluate(client, site)
    assert still_missing.status_code == 409
    assert still_missing.json()["error"]["code"] == "no_snapshot"

    _snapshot(db_engine, site)
    now_ok = _evaluate(client, site)
    assert now_ok.status_code == 201


def test_missing_rule_set_is_reported_when_snapshot_exists(
    client, site, db_engine
):
    with db_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM decision_rule_sets WHERE store_id IS NULL")
        )
    _snapshot(db_engine, site)

    response = _evaluate(client, site)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "rule_set_required"
