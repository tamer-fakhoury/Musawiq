"""Tests, campaigns, and ads: constraints (DB-0.9c)."""

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


def _seed_store_and_concept(conn):
    user_id, store_id = _seed_store(conn)
    concept_id = _insert_product_concept(conn, store_id, user_id)
    return user_id, store_id, concept_id


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


def _insert_post(conn, store_id, created_by):
    return conn.execute(
        text(
            """
            INSERT INTO posts (store_id, name, text_content, created_by)
            VALUES (:store_id, 'Post', '{}'::jsonb, :created_by)
            RETURNING id
            """
        ),
        {"store_id": store_id, "created_by": created_by},
    ).scalar_one()


def _seed_page_and_post(conn):
    user_id, store_id, concept_id = _seed_store_and_concept(conn)
    template_id = _insert_page_template(conn)
    page_id = _insert_landing_page(conn, store_id, concept_id, template_id)
    post_id = _insert_post(conn, store_id, user_id)
    return user_id, store_id, concept_id, page_id, post_id


def _insert_test(
    conn,
    store_id,
    product_concept_id,
    created_by,
    status="draft",
    landing_page_id=None,
    post_id=None,
    primary_conversion="whatsapp_click",
):
    return conn.execute(
        text(
            """
            INSERT INTO tests (
                store_id, product_concept_id, landing_page_id, post_id, name,
                status, primary_conversion, currency, total_budget_minor,
                daily_budget_minor, planned_start_at, planned_end_at, created_by
            )
            VALUES (
                :store_id, :product_concept_id, :landing_page_id, :post_id, 'Test',
                :status, :primary_conversion, 'USD', 100000, 10000,
                now(), now() + interval '7 days', :created_by
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "product_concept_id": product_concept_id,
            "landing_page_id": landing_page_id,
            "post_id": post_id,
            "status": status,
            "primary_conversion": primary_conversion,
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


def _insert_ad_set(conn, store_id, campaign_id, budget_type="daily", budget_minor=10000):
    return conn.execute(
        text(
            """
            INSERT INTO ad_sets (
                store_id, campaign_id, name, status, targeting,
                budget_type, budget_minor, currency, start_at, end_at
            )
            VALUES (
                :store_id, :campaign_id, 'Ad Set', 'draft', '{}'::jsonb,
                :budget_type, :budget_minor, 'USD', now(), now() + interval '7 days'
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "campaign_id": campaign_id,
            "budget_type": budget_type,
            "budget_minor": budget_minor,
        },
    ).scalar_one()


def _insert_ad_variation(
    conn, store_id, adset_id, post_id=None, destination_url=None
):
    return conn.execute(
        text(
            """
            INSERT INTO ad_variations (
                store_id, adset_id, copy_text, post_id, destination_url
            )
            VALUES (:store_id, :adset_id, 'Copy', :post_id, :destination_url)
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "adset_id": adset_id,
            "post_id": post_id,
            "destination_url": destination_url,
        },
    ).scalar_one()


def _insert_tracking_link(
    conn,
    store_id,
    test_id,
    campaign_id,
    token="token-1",
    landing_page_id=None,
    post_id=None,
):
    return conn.execute(
        text(
            """
            INSERT INTO tracking_links (
                store_id, test_id, campaign_id, token, destination_url,
                landing_page_id, post_id
            )
            VALUES (
                :store_id, :test_id, :campaign_id, :token, 'https://example.com',
                :landing_page_id, :post_id
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "test_id": test_id,
            "campaign_id": campaign_id,
            "token": token,
            "landing_page_id": landing_page_id,
            "post_id": post_id,
        },
    ).scalar_one()


def _insert_publication_attempt(
    conn,
    store_id,
    submitted_by,
    campaign_id=None,
    adset_id=None,
    ad_variation_id=None,
):
    return conn.execute(
        text(
            """
            INSERT INTO publication_attempts (
                store_id, campaign_id, adset_id, ad_variation_id, provider,
                attempt_number, status, submitted_by, submitted_at
            )
            VALUES (
                :store_id, :campaign_id, :adset_id, :ad_variation_id, 'meta',
                1, 'pending', :submitted_by, now()
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "campaign_id": campaign_id,
            "adset_id": adset_id,
            "ad_variation_id": ad_variation_id,
            "submitted_by": submitted_by,
        },
    ).scalar_one()


def test_tests_target_check(conn):
    user_id, store_id, concept_id, page_id, post_id = _seed_page_and_post(conn)

    draft_id = _insert_test(conn, store_id, concept_id, user_id, status="draft")
    assert draft_id is not None

    with pytest.raises(DBAPIError):
        _insert_test(
            conn,
            store_id,
            concept_id,
            user_id,
            status="running",
            landing_page_id=page_id,
            post_id=post_id,
        )


def test_tests_primary_conversion_check(conn):
    user_id, store_id, concept_id = _seed_store_and_concept(conn)

    with pytest.raises(DBAPIError):
        _insert_test(
            conn,
            store_id,
            concept_id,
            user_id,
            status="draft",
            primary_conversion="signup",
        )


def test_tests_planned_window_check(conn):
    user_id, store_id, concept_id = _seed_store_and_concept(conn)

    with pytest.raises(DBAPIError):
        conn.execute(
            text(
                """
                INSERT INTO tests (
                    store_id, product_concept_id, name, status, primary_conversion,
                    currency, total_budget_minor, daily_budget_minor,
                    planned_start_at, planned_end_at, created_by
                )
                VALUES (
                    :store_id, :concept_id, 'Test', 'draft', 'whatsapp_click',
                    'USD', 100000, 10000,
                    '2026-01-10T00:00:00Z', '2026-01-01T00:00:00Z', :user_id
                )
                """
            ),
            {
                "store_id": store_id,
                "concept_id": concept_id,
                "user_id": user_id,
            },
        )


def test_ad_sets_allow_null_budget(conn):
    user_id, store_id, concept_id = _seed_store_and_concept(conn)
    test_id = _insert_test(conn, store_id, concept_id, user_id)
    campaign_id = _insert_campaign(conn, store_id, test_id, user_id)

    adset_id = _insert_ad_set(
        conn, store_id, campaign_id, budget_type=None, budget_minor=None
    )
    assert adset_id is not None


def test_ad_variations_target_check(conn):
    user_id, store_id, concept_id = _seed_store_and_concept(conn)
    test_id = _insert_test(conn, store_id, concept_id, user_id)
    campaign_id = _insert_campaign(conn, store_id, test_id, user_id)
    adset_id = _insert_ad_set(conn, store_id, campaign_id)

    with pytest.raises(DBAPIError):
        _insert_ad_variation(conn, store_id, adset_id)


def test_tracking_links_target_check(conn):
    user_id, store_id, concept_id = _seed_store_and_concept(conn)
    test_id = _insert_test(conn, store_id, concept_id, user_id)
    campaign_id = _insert_campaign(conn, store_id, test_id, user_id)

    with pytest.raises(DBAPIError):
        _insert_tracking_link(conn, store_id, test_id, campaign_id)


def test_publication_attempts_target_check(conn):
    user_id, store_id, concept_id = _seed_store_and_concept(conn)
    test_id = _insert_test(conn, store_id, concept_id, user_id)
    campaign_id = _insert_campaign(conn, store_id, test_id, user_id)
    adset_id = _insert_ad_set(conn, store_id, campaign_id)

    with pytest.raises(DBAPIError):
        _insert_publication_attempt(
            conn,
            store_id,
            submitted_by=user_id,
            campaign_id=campaign_id,
            adset_id=adset_id,
        )


def test_tracking_links_token_is_unique(conn):
    user_id, store_id, concept_id, page_id, _ = _seed_page_and_post(conn)
    test_id = _insert_test(conn, store_id, concept_id, user_id)
    campaign_id = _insert_campaign(conn, store_id, test_id, user_id)
    _insert_tracking_link(
        conn,
        store_id,
        test_id,
        campaign_id,
        token="same-token",
        landing_page_id=page_id,
    )

    with pytest.raises(DBAPIError):
        _insert_tracking_link(
            conn,
            store_id,
            test_id,
            campaign_id,
            token="same-token",
            landing_page_id=page_id,
        )
