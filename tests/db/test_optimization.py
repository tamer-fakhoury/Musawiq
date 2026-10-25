"""Optimization tables: constraints (DB-0.11)."""

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


def _insert_campaign(conn, store_id, test_id, created_by):
    return conn.execute(
        text(
            """
            INSERT INTO campaigns (
                store_id, test_id, provider, name, objective, budget_type,
                budget_minor, currency, start_at, end_at, created_by
            )
            VALUES (
                :store_id, :test_id, 'meta', 'Campaign', 'conversions', 'daily',
                10000, 'USD', now(), now() + interval '7 days', :created_by
            )
            RETURNING id
            """
        ),
        {"store_id": store_id, "test_id": test_id, "created_by": created_by},
    ).scalar_one()


def _seed_campaign(conn):
    user_id, store_id = _seed_store(conn)
    concept_id = _insert_product_concept(conn, store_id, user_id)
    test_id = _insert_test(conn, store_id, concept_id, user_id)
    campaign_id = _insert_campaign(conn, store_id, test_id, user_id)
    return user_id, store_id, test_id, campaign_id


def _insert_rule_set(conn, store_id=None, scope="global", campaign_id=None, version=1):
    return conn.execute(
        text(
            """
            INSERT INTO optimization_rule_sets (store_id, scope, campaign_id, version)
            VALUES (:store_id, :scope, :campaign_id, :version)
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "scope": scope,
            "campaign_id": campaign_id,
            "version": version,
        },
    ).scalar_one()


def _insert_finding(
    conn, store_id, campaign_id, rule_set_id, status="underperforming"
):
    return conn.execute(
        text(
            """
            INSERT INTO performance_findings (
                store_id, campaign_id, rule_set_id, status, metric_key,
                observed_value, threshold_value, reason_code,
                data_window_start, data_window_end, evaluated_at
            )
            VALUES (
                :store_id, :campaign_id, :rule_set_id, :status, 'ctr',
                0.0100, 0.0200, 'below_floor',
                now() - interval '7 days', now(), now()
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "campaign_id": campaign_id,
            "rule_set_id": rule_set_id,
            "status": status,
        },
    ).scalar_one()


def _insert_recommendation(conn, store_id, campaign_id, action="pause"):
    return conn.execute(
        text(
            """
            INSERT INTO optimization_recommendations (
                store_id, campaign_id, action, rationale, currency
            )
            VALUES (
                :store_id, :campaign_id, :action, 'Because', 'USD'
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "campaign_id": campaign_id,
            "action": action,
        },
    ).scalar_one()


def _insert_budget_policy(
    conn, store_id, created_by, test_id=None, campaign_id=None
):
    return conn.execute(
        text(
            """
            INSERT INTO budget_policies (
                store_id, test_id, campaign_id, total_cap_minor, daily_cap_minor,
                currency, created_by
            )
            VALUES (
                :store_id, :test_id, :campaign_id, 100000, 10000, 'USD', :created_by
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "test_id": test_id,
            "campaign_id": campaign_id,
            "created_by": created_by,
        },
    ).scalar_one()


def _insert_alert(conn, store_id, severity="warning", type="anomaly"):
    return conn.execute(
        text(
            """
            INSERT INTO alerts (store_id, type, severity, title, message)
            VALUES (:store_id, :type, :severity, 'Alert', 'Message')
            RETURNING id
            """
        ),
        {"store_id": store_id, "type": type, "severity": severity},
    ).scalar_one()


def test_optimization_rule_sets_campaign_scope_check(conn):
    _, store_id = _seed_store(conn)

    with pytest.raises(DBAPIError):
        _insert_rule_set(conn, store_id=store_id, scope="campaign", campaign_id=None)


def test_optimization_rule_sets_unique_nulls_not_distinct(conn):
    _insert_rule_set(conn, store_id=None, scope="global", campaign_id=None, version=1)

    with pytest.raises(DBAPIError):
        _insert_rule_set(
            conn, store_id=None, scope="global", campaign_id=None, version=1
        )


def test_optimization_recommendations_action_check(conn):
    _, store_id, _, campaign_id = _seed_campaign(conn)

    with pytest.raises(DBAPIError):
        _insert_recommendation(conn, store_id, campaign_id, action="delete")


def test_budget_policies_target_check(conn):
    user_id, store_id = _seed_store(conn)

    with pytest.raises(DBAPIError):
        _insert_budget_policy(conn, store_id, user_id)


def test_alerts_severity_check(conn):
    _, store_id = _seed_store(conn)

    with pytest.raises(DBAPIError):
        _insert_alert(conn, store_id, severity="fatal")


def test_performance_findings_status_check(conn):
    _, store_id, _, campaign_id = _seed_campaign(conn)
    rule_set_id = _insert_rule_set(conn, store_id=store_id, scope="store")

    with pytest.raises(DBAPIError):
        _insert_finding(conn, store_id, campaign_id, rule_set_id, status="bad")
