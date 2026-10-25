"""Decision and investment tables: constraints (DB-0.12)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def _insert_user(conn, email="owner@example.com"):
    return conn.execute(
        text(
            """
            INSERT INTO users (email, full_name, role, status)
            VALUES (:email, 'Test User', 'owner', 'active')
            RETURNING id
            """
        ),
        {"email": email},
    ).scalar_one()


def _insert_store(conn, owner_user_id, slug="demo-store"):
    return conn.execute(
        text(
            """
            INSERT INTO stores (
                owner_user_id, name, slug, status,
                default_currency, default_language, timezone, country_code,
                onboarding_status
            )
            VALUES (
                :owner_user_id, 'Demo Store', :slug, 'active',
                'USD', 'en', 'UTC', 'US', 'completed'
            )
            RETURNING id
            """
        ),
        {"owner_user_id": owner_user_id, "slug": slug},
    ).scalar_one()


def _seed_store(conn, email="owner@example.com", slug="demo-store"):
    user_id = _insert_user(conn, email=email)
    store_id = _insert_store(conn, user_id, slug=slug)
    return user_id, store_id


def _insert_category(conn, slug="electronics"):
    return conn.execute(
        text(
            """
            INSERT INTO categories (name, slug)
            VALUES ('Electronics', :slug)
            RETURNING id
            """
        ),
        {"slug": slug},
    ).scalar_one()


def _insert_product_concept(conn, store_id, created_by, category_id=None):
    if category_id is None:
        category_id = _insert_category(conn)
    return conn.execute(
        text(
            """
            INSERT INTO product_concepts (
                store_id, name, category_id, price_minor, cost_minor, currency,
                gross_margin_bp, created_by
            )
            VALUES (
                :store_id, 'Concept', :category_id, 1000, 400, 'USD', 6000,
                :created_by
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "category_id": category_id,
            "created_by": created_by,
        },
    ).scalar_one()


def _insert_test(conn, store_id, product_concept_id, created_by):
    return conn.execute(
        text(
            """
            INSERT INTO tests (
                store_id, product_concept_id, name, status, primary_conversion,
                currency, total_budget_minor, daily_budget_minor,
                planned_start_at, planned_end_at, created_by
            )
            VALUES (
                :store_id, :product_concept_id, 'Test', 'draft', 'whatsapp_click',
                'USD', 100000, 10000, now(), now() + interval '7 days', :created_by
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "product_concept_id": product_concept_id,
            "created_by": created_by,
        },
    ).scalar_one()


def _seed_test(conn):
    user_id, store_id = _seed_store(conn)
    concept_id = _insert_product_concept(conn, store_id, user_id)
    test_id = _insert_test(conn, store_id, concept_id, user_id)
    return user_id, store_id, test_id


def _insert_decision_rule_set(conn, store_id=None, category_id=None, version=1):
    return conn.execute(
        text(
            """
            INSERT INTO decision_rule_sets (store_id, category_id, version)
            VALUES (:store_id, :category_id, :version)
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "category_id": category_id,
            "version": version,
        },
    ).scalar_one()


def _insert_snapshot(conn, store_id, test_id):
    return conn.execute(
        text(
            """
            INSERT INTO test_result_snapshots (
                store_id, test_id, period_start, period_end, currency,
                spend_minor, impressions, clicks, tracked_conversions,
                confirmed_deposits, data_completeness, captured_at
            )
            VALUES (
                :store_id, :test_id, now() - interval '7 days', now(), 'USD',
                100000, 1000, 100, 10, 5, 0.9500, now()
            )
            RETURNING id
            """
        ),
        {"store_id": store_id, "test_id": test_id},
    ).scalar_one()


def _insert_verdict(
    conn,
    store_id,
    test_id,
    result_snapshot_id,
    decision_rule_set_id,
    outcome="go",
):
    return conn.execute(
        text(
            """
            INSERT INTO verdicts (
                store_id, test_id, result_snapshot_id, decision_rule_set_id,
                outcome, is_conclusive, primary_reason, rule_trace
            )
            VALUES (
                :store_id, :test_id, :result_snapshot_id, :decision_rule_set_id,
                :outcome, true, 'Reason', '{}'::jsonb
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "test_id": test_id,
            "result_snapshot_id": result_snapshot_id,
            "decision_rule_set_id": decision_rule_set_id,
            "outcome": outcome,
        },
    ).scalar_one()


def _insert_investment_profile(
    conn,
    store_id,
    test_id,
    version=1,
    is_current=False,
    payment_fee_bp=0,
    supplier_moq=1,
):
    return conn.execute(
        text(
            """
            INSERT INTO investment_profiles (
                store_id, test_id, version, unit_cost_minor, selling_price_minor,
                payment_fee_bp, available_budget_minor, target_margin_bp,
                supplier_moq, lead_time_days, currency, is_current
            )
            VALUES (
                :store_id, :test_id, :version, 1000, 2000,
                :payment_fee_bp, 100000, 3000, :supplier_moq, 7, 'USD', :is_current
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "test_id": test_id,
            "version": version,
            "is_current": is_current,
            "payment_fee_bp": payment_fee_bp,
            "supplier_moq": supplier_moq,
        },
    ).scalar_one()


def _insert_investment_recommendation(
    conn, store_id, test_id, investment_profile_id, version=1, is_current=False
):
    return conn.execute(
        text(
            """
            INSERT INTO investment_recommendations (
                store_id, test_id, investment_profile_id, version, summary,
                assumptions_snapshot, is_current
            )
            VALUES (
                :store_id, :test_id, :investment_profile_id, :version, 'Summary',
                '{}'::jsonb, :is_current
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "test_id": test_id,
            "investment_profile_id": investment_profile_id,
            "version": version,
            "is_current": is_current,
        },
    ).scalar_one()


def _seed_recommendation(conn):
    user_id, store_id, test_id = _seed_test(conn)
    profile_id = _insert_investment_profile(conn, store_id, test_id)
    recommendation_id = _insert_investment_recommendation(
        conn, store_id, test_id, profile_id
    )
    return store_id, recommendation_id


def _insert_demand_estimate(
    conn, store_id, investment_recommendation_id, low=100, base=200, high=300
):
    return conn.execute(
        text(
            """
            INSERT INTO demand_estimates (
                store_id, investment_recommendation_id, low_units, base_units,
                high_units, assumptions, confidence
            )
            VALUES (
                :store_id, :investment_recommendation_id, :low, :base,
                :high, '{}'::jsonb, 'high'
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "investment_recommendation_id": investment_recommendation_id,
            "low": low,
            "base": base,
            "high": high,
        },
    ).scalar_one()


def _insert_quantity_scenario(
    conn,
    store_id,
    investment_recommendation_id,
    label="base",
    overstock_risk="low",
    low=100,
    high=200,
):
    return conn.execute(
        text(
            """
            INSERT INTO quantity_scenarios (
                store_id, investment_recommendation_id, label, quantity,
                inventory_cost_minor, expected_units_sold_low,
                expected_units_sold_high, revenue_low_minor, revenue_high_minor,
                profit_low_minor, profit_high_minor, sell_through_low,
                sell_through_high, overstock_risk, stockout_risk, is_feasible
            )
            VALUES (
                :store_id, :investment_recommendation_id, :label, 200,
                100000, :low, :high, 200000, 400000, 100000, 300000,
                0.5000, 1.0000, :overstock_risk, 'low', true
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "investment_recommendation_id": investment_recommendation_id,
            "label": label,
            "overstock_risk": overstock_risk,
            "low": low,
            "high": high,
        },
    ).scalar_one()


def test_verdicts_outcome_check(conn):
    _, store_id, test_id = _seed_test(conn)
    rule_set_id = _insert_decision_rule_set(conn)
    snapshot_id = _insert_snapshot(conn, store_id, test_id)

    with pytest.raises(DBAPIError):
        _insert_verdict(
            conn,
            store_id,
            test_id,
            snapshot_id,
            rule_set_id,
            outcome="maybe",
        )


def test_verdicts_reject_update(conn):
    _, store_id, test_id = _seed_test(conn)
    rule_set_id = _insert_decision_rule_set(conn)
    snapshot_id = _insert_snapshot(conn, store_id, test_id)
    _insert_verdict(conn, store_id, test_id, snapshot_id, rule_set_id)

    with pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text("UPDATE verdicts SET is_conclusive = false"))


def test_test_result_snapshots_reject_delete(conn):
    _, store_id, test_id = _seed_test(conn)
    _insert_snapshot(conn, store_id, test_id)

    with pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text("DELETE FROM test_result_snapshots"))


def test_investment_profiles_version_is_unique(conn):
    _, store_id, test_id = _seed_test(conn)
    _insert_investment_profile(conn, store_id, test_id, version=1)

    with pytest.raises(DBAPIError):
        _insert_investment_profile(conn, store_id, test_id, version=1)


def test_investment_recommendations_version_is_unique(conn):
    _, store_id, test_id = _seed_test(conn)
    profile_id = _insert_investment_profile(conn, store_id, test_id)
    _insert_investment_recommendation(conn, store_id, test_id, profile_id, version=1)

    with pytest.raises(DBAPIError):
        _insert_investment_recommendation(
            conn, store_id, test_id, profile_id, version=1
        )


def test_only_one_current_investment_profile_per_test(conn):
    _, store_id, test_id = _seed_test(conn)
    _insert_investment_profile(conn, store_id, test_id, version=1, is_current=True)

    with pytest.raises(DBAPIError):
        _insert_investment_profile(
            conn, store_id, test_id, version=2, is_current=True
        )


def test_demand_estimates_range_check(conn):
    store_id, recommendation_id = _seed_recommendation(conn)

    with pytest.raises(DBAPIError):
        _insert_demand_estimate(
            conn, store_id, recommendation_id, low=300, base=200, high=400
        )


def test_quantity_scenarios_label_check(conn):
    store_id, recommendation_id = _seed_recommendation(conn)

    with pytest.raises(DBAPIError):
        _insert_quantity_scenario(conn, store_id, recommendation_id, label="extreme")


def test_quantity_scenarios_overstock_risk_check(conn):
    store_id, recommendation_id = _seed_recommendation(conn)

    with pytest.raises(DBAPIError):
        _insert_quantity_scenario(
            conn, store_id, recommendation_id, overstock_risk="extreme"
        )


def test_quantity_scenarios_units_range_check(conn):
    store_id, recommendation_id = _seed_recommendation(conn)

    with pytest.raises(DBAPIError):
        _insert_quantity_scenario(conn, store_id, recommendation_id, low=300, high=200)


def test_investment_profiles_payment_fee_check(conn):
    _, store_id, test_id = _seed_test(conn)

    with pytest.raises(DBAPIError):
        _insert_investment_profile(conn, store_id, test_id, payment_fee_bp=10001)


def test_investment_profiles_supplier_moq_check(conn):
    _, store_id, test_id = _seed_test(conn)

    with pytest.raises(DBAPIError):
        _insert_investment_profile(conn, store_id, test_id, supplier_moq=0)
