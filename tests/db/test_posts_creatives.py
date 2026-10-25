"""Posts and creatives: constraints (DB-0.9b)."""

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


def _insert_creative(conn, store_id, external_url="https://example.com/creative.png"):
    return conn.execute(
        text(
            """
            INSERT INTO creatives (store_id, source, type, external_url)
            VALUES (:store_id, 'uploaded', 'image', :external_url)
            RETURNING id
            """
        ),
        {"store_id": store_id, "external_url": external_url},
    ).scalar_one()


def _insert_post(conn, store_id, created_by, slug=None):
    return conn.execute(
        text(
            """
            INSERT INTO posts (store_id, name, slug, text_content, created_by)
            VALUES (:store_id, 'Post', :slug, '{}'::jsonb, :created_by)
            RETURNING id
            """
        ),
        {"store_id": store_id, "slug": slug, "created_by": created_by},
    ).scalar_one()


def _insert_post_creative(conn, store_id, post_id, creative_id, position=0):
    return conn.execute(
        text(
            """
            INSERT INTO post_creatives (store_id, post_id, creative_id, position)
            VALUES (:store_id, :post_id, :creative_id, :position)
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "post_id": post_id,
            "creative_id": creative_id,
            "position": position,
        },
    ).scalar_one()


def _insert_creative_variant(
    conn, store_id, creative_id, external_url="https://example.com/variant.png"
):
    return conn.execute(
        text(
            """
            INSERT INTO creative_variants (store_id, creative_id, external_url)
            VALUES (:store_id, :creative_id, :external_url)
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "creative_id": creative_id,
            "external_url": external_url,
        },
    ).scalar_one()


def _insert_order_channel_for_post(conn, store_id, post_id):
    return conn.execute(
        text(
            """
            INSERT INTO order_channels (store_id, post_id, type, whatsapp_number)
            VALUES (:store_id, :post_id, 'whatsapp', '+15555550100')
            RETURNING id
            """
        ),
        {"store_id": store_id, "post_id": post_id},
    ).scalar_one()


def test_post_creatives_unique_creative(conn):
    user_id, store_id = _seed_store(conn)
    post_id = _insert_post(conn, store_id, user_id)
    creative_a = _insert_creative(conn, store_id)
    _insert_post_creative(conn, store_id, post_id, creative_a, position=0)

    with pytest.raises(DBAPIError):
        _insert_post_creative(conn, store_id, post_id, creative_a, position=1)


def test_post_creatives_unique_position(conn):
    user_id, store_id = _seed_store(conn)
    post_id = _insert_post(conn, store_id, user_id)
    creative_a = _insert_creative(conn, store_id)
    creative_b = _insert_creative(
        conn, store_id, external_url="https://example.com/second.png"
    )
    _insert_post_creative(conn, store_id, post_id, creative_a, position=0)

    with pytest.raises(DBAPIError):
        _insert_post_creative(conn, store_id, post_id, creative_b, position=0)


def test_creatives_require_media_source(conn):
    _, store_id = _seed_store(conn)

    with pytest.raises(DBAPIError):
        conn.execute(
            text(
                """
                INSERT INTO creatives (store_id, source, type)
                VALUES (:store_id, 'uploaded', 'image')
                """
            ),
            {"store_id": store_id},
        )


def test_creative_variants_require_media_source(conn):
    _, store_id = _seed_store(conn)
    creative_id = _insert_creative(conn, store_id)

    with pytest.raises(DBAPIError):
        conn.execute(
            text(
                """
                INSERT INTO creative_variants (store_id, creative_id)
                VALUES (:store_id, :creative_id)
                """
            ),
            {"store_id": store_id, "creative_id": creative_id},
        )


def test_creative_variants_accept_external_url(conn):
    _, store_id = _seed_store(conn)
    creative_id = _insert_creative(conn, store_id)

    variant_id = _insert_creative_variant(conn, store_id, creative_id)
    assert variant_id is not None


def test_posts_slug_partial_unique(conn):
    user_id, store_id = _seed_store(conn)
    _insert_post(conn, store_id, user_id, slug=None)
    _insert_post(conn, store_id, user_id, slug=None)

    count = conn.execute(
        text("SELECT count(*) FROM posts WHERE slug IS NULL")
    ).scalar_one()
    assert count == 2

    _insert_post(conn, store_id, user_id, slug="same-slug")

    with pytest.raises(DBAPIError):
        _insert_post(conn, store_id, user_id, slug="same-slug")


def test_order_channels_post_id_fk(conn):
    user_id, store_id = _seed_store(conn)
    post_id = _insert_post(conn, store_id, user_id)

    channel_id = _insert_order_channel_for_post(conn, store_id, post_id)
    assert channel_id is not None

    with pytest.raises(DBAPIError):
        _insert_order_channel_for_post(conn, store_id, uuid.uuid4())


def test_post_creatives_position_check(conn):
    user_id, store_id = _seed_store(conn)
    post_id = _insert_post(conn, store_id, user_id)
    creative_id = _insert_creative(conn, store_id)

    with pytest.raises(DBAPIError):
        _insert_post_creative(conn, store_id, post_id, creative_id, position=-1)
