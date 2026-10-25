"""Audience and store-context tables: constraints (DB-0.6)."""

from __future__ import annotations

import uuid

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


def _insert_category(conn, slug="electronics", parent_id=None):
    return conn.execute(
        text(
            """
            INSERT INTO categories (parent_id, name, slug)
            VALUES (:parent_id, 'Electronics', :slug)
            RETURNING id
            """
        ),
        {"parent_id": parent_id, "slug": slug},
    ).scalar_one()


def _insert_niche(conn, category_id, store_id=None, slug="phones"):
    return conn.execute(
        text(
            """
            INSERT INTO niches (category_id, store_id, name, slug)
            VALUES (:category_id, :store_id, 'Phones', :slug)
            RETURNING id
            """
        ),
        {
            "category_id": category_id,
            "store_id": store_id,
            "slug": slug,
        },
    ).scalar_one()


def _insert_audience_profile(
    conn, store_id, created_by, version=1, is_current=False
):
    return conn.execute(
        text(
            """
            INSERT INTO audience_profiles (
                store_id, version, status, is_current, created_by
            )
            VALUES (:store_id, :version, 'active', :is_current, :created_by)
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "version": version,
            "is_current": is_current,
            "created_by": created_by,
        },
    ).scalar_one()


def _insert_audience_segment(
    conn, store_id, audience_profile_id, age_min=18, age_max=65
):
    return conn.execute(
        text(
            """
            INSERT INTO audience_segments (
                store_id, audience_profile_id, label, age_min, age_max
            )
            VALUES (:store_id, :audience_profile_id, 'Segment', :age_min, :age_max)
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "audience_profile_id": audience_profile_id,
            "age_min": age_min,
            "age_max": age_max,
        },
    ).scalar_one()


def _insert_feedback_item(conn, store_id, source="manual"):
    return conn.execute(
        text(
            """
            INSERT INTO feedback_items (store_id, source, "text", captured_at)
            VALUES (:store_id, :source, 'Great product', now())
            RETURNING id
            """
        ),
        {"store_id": store_id, "source": source},
    ).scalar_one()


def _insert_product(conn, store_id, category_id=None):
    return conn.execute(
        text(
            """
            INSERT INTO products (store_id, name, currency, source, category_id)
            VALUES (:store_id, 'Product', 'USD', 'manual', :category_id)
            RETURNING id
            """
        ),
        {"store_id": store_id, "category_id": category_id},
    ).scalar_one()


def test_categories_slug_is_unique(conn):
    _insert_category(conn)

    with pytest.raises(DBAPIError):
        _insert_category(conn)


def test_global_niches_may_share_slug(conn):
    category_id = _insert_category(conn)
    _insert_niche(conn, category_id, slug="phones")
    _insert_niche(conn, category_id, slug="phones")

    count = conn.execute(
        text("SELECT count(*) FROM niches WHERE store_id IS NULL")
    ).scalar_one()
    assert count == 2


def test_store_niches_must_be_unique_per_store(conn):
    _, store_id = _seed_store(conn)
    category_id = _insert_category(conn)
    _insert_niche(conn, category_id, store_id=store_id, slug="phones")

    with pytest.raises(DBAPIError):
        _insert_niche(conn, category_id, store_id=store_id, slug="phones")


def test_audience_profiles_version_is_unique_per_store(conn):
    user_id, store_id = _seed_store(conn)
    _insert_audience_profile(conn, store_id, user_id, version=1)

    with pytest.raises(DBAPIError):
        _insert_audience_profile(conn, store_id, user_id, version=1)


def test_only_one_current_audience_profile_per_store(conn):
    user_id, store_id = _seed_store(conn)
    _insert_audience_profile(conn, store_id, user_id, version=1, is_current=True)

    with pytest.raises(DBAPIError):
        _insert_audience_profile(conn, store_id, user_id, version=2, is_current=True)


def test_audience_segments_reject_inverted_age_range(conn):
    user_id, store_id = _seed_store(conn)
    profile_id = _insert_audience_profile(conn, store_id, user_id)

    with pytest.raises(DBAPIError):
        _insert_audience_segment(conn, store_id, profile_id, age_min=40, age_max=30)


def test_feedback_items_source_check(conn):
    _, store_id = _seed_store(conn)

    with pytest.raises(DBAPIError):
        _insert_feedback_item(conn, store_id, source="email")


def test_products_category_id_fk(conn):
    _, store_id = _seed_store(conn)
    category_id = _insert_category(conn)

    product_id = _insert_product(conn, store_id, category_id=category_id)
    assert product_id is not None

    with pytest.raises(DBAPIError):
        _insert_product(conn, store_id, category_id=uuid.uuid4())
