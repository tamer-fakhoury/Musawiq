"""FR-5.1.7: test extension with caps and verdict recomputation."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

from musawiq.auth.errors import PermissionDenied


def _headers(site, role="owner"):
    return {
        "X-Store-Id": str(site.store_id),
        "X-User-Id": str(site.user_id),
        "X-User-Role": role,
    }


def _rules(client, site):
    response = client.post(
        "/decision-rule-sets",
        json={
            "min_spend_minor": 10000,
            "min_clicks": 100,
            "min_conversions": 5,
            "min_conversion_rate": 0.02,
            "max_cost_per_conversion_minor": 2000,
            "rules": {"schema_version": 1},
        },
        headers=_headers(site),
    )
    assert response.status_code == 201, response.text


def _snapshot(db_engine, site):
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=2)
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
                    20000, 1000, 500, 20, 5, 0.04, 1000, 0.5, '{}', now()
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


def _extendable(client, site, db_engine):
    _rules(client, site)
    _snapshot(db_engine, site)
    verdict = client.post(
        f"/tests/{site.test_id}/verdicts", headers=_headers(site)
    )
    assert verdict.status_code == 201
    assert verdict.json()["outcome"] == "extend_test"


def _extend(client, site, **overrides):
    planned_end = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)
    payload = {
        "new_end_at": (planned_end + dt.timedelta(days=7)).isoformat(),
        "added_budget_minor": 5000,
        "reason": "Need more evidence",
    }
    payload.update(overrides)
    return client.post(
        f"/tests/{site.test_id}/extensions",
        json=payload,
        headers=_headers(site),
    )


def _test_row(db_engine, site):
    with db_engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT status, planned_end_at, total_budget_minor, "
                "actual_end_at FROM tests WHERE id = :id"
            ),
            {"id": site.test_id},
        ).mappings().one()


def test_extension_records_window_budget_and_new_verdict(
    client, site, db_engine
):
    _extendable(client, site, db_engine)
    before = _test_row(db_engine, site)
    verdicts_before = client.get(
        f"/tests/{site.test_id}/verdicts", headers=_headers(site)
    ).json()
    snapshots_before = db_engine.connect().execute(
        text(
            "SELECT count(*) FROM test_result_snapshots WHERE test_id = :id"
        ),
        {"id": site.test_id},
    ).scalar()

    response = _extend(client, site)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["previous_end_at"] == before["planned_end_at"].isoformat()
    assert body["added_budget_minor"] == 5000
    assert body["recompute_policy"] == "combined"
    assert body["verdict_outcome"] == "extend_test"

    after = _test_row(db_engine, site)
    assert after["status"] == "extended"
    assert after["planned_end_at"] == dt.datetime.fromisoformat(
        body["new_end_at"]
    )
    assert after["total_budget_minor"] == before["total_budget_minor"] + 5000
    assert after["actual_end_at"] is None

    with db_engine.connect() as conn:
        extensions = conn.execute(
            text(
                "SELECT count(*) FROM test_extensions WHERE test_id = :id"
            ),
            {"id": site.test_id},
        ).scalar_one()
        snapshots_after = conn.execute(
            text(
                "SELECT count(*) FROM test_result_snapshots "
                "WHERE test_id = :id"
            ),
            {"id": site.test_id},
        ).scalar_one()
    assert extensions == 1
    assert snapshots_after == snapshots_before + 1

    verdicts_after = client.get(
        f"/tests/{site.test_id}/verdicts", headers=_headers(site)
    ).json()
    assert len(verdicts_after) == len(verdicts_before) + 1
    latest = verdicts_after[0]
    assert latest["rule_trace"]["recompute_policy"] == "combined"
    assert any(
        item["id"] == verdicts_before[0]["id"] for item in verdicts_after[1:]
    )


def test_extension_is_rejected_above_budget_caps(client, site, db_engine):
    _extendable(client, site, db_engine)
    test = _test_row(db_engine, site)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO budget_policies (
                    store_id, test_id, total_cap_minor, daily_cap_minor,
                    currency, enforcement, is_active, created_by
                ) VALUES (
                    :store_id, :test_id, :total_cap, 100000,
                    'USD', 'hard', true, :user_id
                )
                """
            ),
            {
                "store_id": site.store_id,
                "test_id": site.test_id,
                "total_cap": test["total_budget_minor"] + 1000,
                "user_id": site.user_id,
            },
        )

    response = _extend(client, site)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "budget_cap_exceeded"

    with db_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM test_extensions WHERE test_id = :id"),
            {"id": site.test_id},
        ).scalar_one()
    assert count == 0


def test_extension_validates_window_policy_and_role(client, site, db_engine):
    _extendable(client, site, db_engine)

    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat()
    bad_window = _extend(client, site, new_end_at=past)
    assert bad_window.status_code == 422
    assert bad_window.json()["error"]["code"] == "invalid_window"

    bad_policy = _extend(client, site, recompute_policy="whatever")
    assert bad_policy.status_code == 422

    with pytest.raises(PermissionDenied):
        client.post(
            f"/tests/{site.test_id}/extensions",
            json={
                "new_end_at": (
                    dt.datetime.now(dt.timezone.utc)
                    + dt.timedelta(days=40)
                ).isoformat(),
                "added_budget_minor": 1000,
            },
            headers=_headers(site, role="analyst"),
        )


def test_new_window_policy_is_recorded_with_verdict(client, site, db_engine):
    _extendable(client, site, db_engine)

    response = _extend(client, site, recompute_policy="new_window")

    assert response.status_code == 201
    body = response.json()
    assert body["recompute_policy"] == "new_window"

    verdicts = client.get(
        f"/tests/{site.test_id}/verdicts", headers=_headers(site)
    ).json()
    assert verdicts[0]["rule_trace"]["recompute_policy"] == "new_window"

    with db_engine.connect() as conn:
        period = conn.execute(
            text(
                "SELECT period_start FROM test_result_snapshots "
                "WHERE id = :id"
            ),
            {"id": body["snapshot_id"]},
        ).scalar_one()
        extension = conn.execute(
            text(
                "SELECT previous_end_at FROM test_extensions WHERE id = :id"
            ),
            {"id": body["id"]},
        ).scalar_one()
    assert period == extension
