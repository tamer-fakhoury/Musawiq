"""Measurement tables: constraints and append-only behavior (DB-0.10)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

PERIOD_START = "2026-01-01T00:00:00Z"
PERIOD_END = "2026-01-02T00:00:00Z"


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


def _insert_page_template(conn, key="pdp", version=1):
    return conn.execute(
        text(
            """
            INSERT INTO page_templates (key, version, name, schema)
            VALUES (:key, :version, 'Product Page', '{}'::jsonb)
            RETURNING id
            """
        ),
        {"key": key, "version": version},
    ).scalar_one()


def _insert_landing_page(conn, store_id, product_concept_id, template_id):
    return conn.execute(
        text(
            """
            INSERT INTO landing_pages (
                store_id, product_concept_id, slug, template_id, language, currency
            )
            VALUES (
                :store_id, :product_concept_id, 'landing-page', :template_id,
                'en', 'USD'
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "product_concept_id": product_concept_id,
            "template_id": template_id,
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


def _insert_order(conn, store_id):
    return conn.execute(
        text(
            """
            INSERT INTO orders (store_id, origin, status, currency, placed_at)
            VALUES (:store_id, 'cod', 'pending', 'USD', now())
            RETURNING id
            """
        ),
        {"store_id": store_id},
    ).scalar_one()


def _insert_event(
    conn,
    store_id,
    event_id=None,
    event_type="page_view",
    source="web",
):
    return conn.execute(
        text(
            """
            INSERT INTO events (store_id, event_id, event_type, source, occurred_at)
            VALUES (:store_id, :event_id, :event_type, :source, now())
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "event_id": event_id or uuid.uuid4(),
            "event_type": event_type,
            "source": source,
        },
    ).scalar_one()


def _insert_attribution(
    conn,
    store_id,
    subject_type="event",
    subject_id=None,
):
    return conn.execute(
        text(
            """
            INSERT INTO attributions (
                store_id, subject_type, subject_id, model, window_seconds,
                is_attributed, confidence, resolved_at
            )
            VALUES (
                :store_id, :subject_type, :subject_id, 'last_touch', 86400,
                true, 0.9000, now()
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "subject_type": subject_type,
            "subject_id": subject_id or uuid.uuid4(),
        },
    ).scalar_one()


def _insert_deposit(
    conn,
    store_id,
    order_id,
    status="pending",
    amount_minor=1000,
):
    return conn.execute(
        text(
            """
            INSERT INTO deposits (
                store_id, order_id, status, amount_minor, currency, method
            )
            VALUES (
                :store_id, :order_id, :status, :amount_minor, 'USD', 'manual'
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "order_id": order_id,
            "status": status,
            "amount_minor": amount_minor,
        },
    ).scalar_one()


def _insert_metric_snapshot(
    conn,
    store_id,
    test_id,
    campaign_id,
    adset_id=None,
    ad_variation_id=None,
):
    return conn.execute(
        text(
            """
            INSERT INTO metric_snapshots (
                store_id, test_id, provider, campaign_id, adset_id, ad_variation_id,
                period_start, period_end, snapshot_at, currency, spend_minor,
                impressions, reach, clicks
            )
            VALUES (
                :store_id, :test_id, 'meta', :campaign_id, :adset_id, :ad_variation_id,
                :period_start, :period_end, now(), 'USD', 1000, 100, 50, 10
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "test_id": test_id,
            "campaign_id": campaign_id,
            "adset_id": adset_id,
            "ad_variation_id": ad_variation_id,
            "period_start": PERIOD_START,
            "period_end": PERIOD_END,
        },
    ).scalar_one()


def _insert_tracking_session(conn, store_id, landing_page_id, consent_state="unknown"):
    return conn.execute(
        text(
            """
            INSERT INTO tracking_sessions (
                store_id, landing_page_id, user_agent, ip_hash,
                consent_state, started_at, last_seen_at
            )
            VALUES (
                :store_id, :landing_page_id, 'test-agent', repeat('a', 64),
                :consent_state, now(), now()
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "landing_page_id": landing_page_id,
            "consent_state": consent_state,
        },
    ).scalar_one()


def _seed_test_and_campaign(conn):
    user_id, store_id = _seed_store(conn)
    concept_id = _insert_product_concept(conn, store_id, user_id)
    test_id = _insert_test(conn, store_id, concept_id, user_id)
    campaign_id = _insert_campaign(conn, store_id, test_id, user_id)
    return user_id, store_id, test_id, campaign_id


def test_events_event_id_is_unique(conn):
    _, store_id = _seed_store(conn)
    event_id = uuid.uuid4()
    _insert_event(conn, store_id, event_id=event_id)

    with pytest.raises(DBAPIError):
        _insert_event(conn, store_id, event_id=event_id)


def test_events_event_type_fk(conn):
    _, store_id = _seed_store(conn)

    with pytest.raises(DBAPIError):
        _insert_event(conn, store_id, event_type="unknown_event")


def test_events_source_check(conn):
    _, store_id = _seed_store(conn)

    with pytest.raises(DBAPIError):
        _insert_event(conn, store_id, source="api")


def test_events_reject_update(conn):
    _, store_id = _seed_store(conn)
    _insert_event(conn, store_id)

    with pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text("UPDATE events SET is_bot = true"))


def test_events_reject_delete(conn):
    _, store_id = _seed_store(conn)
    _insert_event(conn, store_id)

    with pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text("DELETE FROM events"))


def test_attributions_reject_update(conn):
    _, store_id = _seed_store(conn)
    _insert_attribution(conn, store_id)

    with pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text("UPDATE attributions SET is_attributed = false"))


def test_attributions_subject_is_unique(conn):
    _, store_id = _seed_store(conn)
    subject_id = uuid.uuid4()
    _insert_attribution(conn, store_id, subject_id=subject_id)

    with pytest.raises(DBAPIError):
        _insert_attribution(conn, store_id, subject_id=subject_id)


def test_deposits_status_check(conn):
    _, store_id = _seed_store(conn)
    order_id = _insert_order(conn, store_id)

    with pytest.raises(DBAPIError):
        _insert_deposit(conn, store_id, order_id, status="cancelled")


def test_deposits_amount_check(conn):
    _, store_id = _seed_store(conn)
    order_id = _insert_order(conn, store_id)

    with pytest.raises(DBAPIError):
        _insert_deposit(conn, store_id, order_id, amount_minor=-1)


def test_metric_snapshots_unique_nulls_not_distinct(conn):
    _, store_id, test_id, campaign_id = _seed_test_and_campaign(conn)
    _insert_metric_snapshot(conn, store_id, test_id, campaign_id)

    with pytest.raises(DBAPIError):
        _insert_metric_snapshot(conn, store_id, test_id, campaign_id)


def test_tracking_sessions_consent_state_check(conn):
    user_id, store_id = _seed_store(conn)
    concept_id = _insert_product_concept(conn, store_id, user_id)
    template_id = _insert_page_template(conn)
    page_id = _insert_landing_page(conn, store_id, concept_id, template_id)

    with pytest.raises(DBAPIError):
        _insert_tracking_session(conn, store_id, page_id, consent_state="maybe")
