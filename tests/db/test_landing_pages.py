"""Landing pages and order channels: constraints (DB-0.9a)."""

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


def _insert_landing_page(
    conn,
    store_id,
    product_concept_id,
    template_id,
    slug="landing-page",
    status="draft",
):
    return conn.execute(
        text(
            """
            INSERT INTO landing_pages (
                store_id, product_concept_id, slug, status, template_id,
                language, currency
            )
            VALUES (
                :store_id, :product_concept_id, :slug, :status, :template_id,
                'en', 'USD'
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "product_concept_id": product_concept_id,
            "slug": slug,
            "status": status,
            "template_id": template_id,
        },
    ).scalar_one()


def _insert_page_version(conn, store_id, landing_page_id, created_by, version=1):
    return conn.execute(
        text(
            """
            INSERT INTO page_versions (
                store_id, landing_page_id, version, content, price_minor,
                currency, generated_by, created_by
            )
            VALUES (
                :store_id, :landing_page_id, :version, '{}'::jsonb, 1000,
                'USD', 'manual', :created_by
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "landing_page_id": landing_page_id,
            "version": version,
            "created_by": created_by,
        },
    ).scalar_one()


def _insert_order_channel(
    conn,
    store_id,
    landing_page_id=None,
    post_id=None,
    type="whatsapp",
    whatsapp_number="+15555550100",
    cod_form_schema=None,
):
    return conn.execute(
        text(
            """
            INSERT INTO order_channels (
                store_id, landing_page_id, post_id, type,
                whatsapp_number, cod_form_schema
            )
            VALUES (
                :store_id, :landing_page_id, :post_id, :type,
                :whatsapp_number, :cod_form_schema
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "landing_page_id": landing_page_id,
            "post_id": post_id,
            "type": type,
            "whatsapp_number": whatsapp_number,
            "cod_form_schema": cod_form_schema,
        },
    ).scalar_one()


def _seed_landing_page(conn):
    user_id, store_id = _seed_store(conn)
    category_id = _insert_category(conn)
    concept_id = _insert_product_concept(conn, store_id, user_id, category_id=category_id)
    template_id = _insert_page_template(conn)
    page_id = _insert_landing_page(conn, store_id, concept_id, template_id)
    return user_id, store_id, page_id


def test_landing_pages_slug_is_unique(conn):
    user_id, store_id = _seed_store(conn)
    category_id = _insert_category(conn)
    concept_id = _insert_product_concept(conn, store_id, user_id, category_id=category_id)
    template_id = _insert_page_template(conn)
    _insert_landing_page(conn, store_id, concept_id, template_id, slug="same-slug")

    with pytest.raises(DBAPIError):
        _insert_landing_page(conn, store_id, concept_id, template_id, slug="same-slug")


def test_page_versions_are_unique_per_page(conn):
    user_id, store_id, page_id = _seed_landing_page(conn)
    _insert_page_version(conn, store_id, page_id, user_id, version=1)

    with pytest.raises(DBAPIError):
        _insert_page_version(conn, store_id, page_id, user_id, version=1)


def test_order_channels_reject_both_page_and_post(conn):
    _, store_id, page_id = _seed_landing_page(conn)

    with pytest.raises(DBAPIError):
        _insert_order_channel(
            conn, store_id, landing_page_id=page_id, post_id=uuid.uuid4()
        )


def test_order_channels_reject_no_target(conn):
    _, store_id, _ = _seed_landing_page(conn)

    with pytest.raises(DBAPIError):
        _insert_order_channel(conn, store_id, landing_page_id=None, post_id=None)


def test_order_channels_whatsapp_requires_number(conn):
    _, store_id, page_id = _seed_landing_page(conn)

    with pytest.raises(DBAPIError):
        _insert_order_channel(
            conn,
            store_id,
            landing_page_id=page_id,
            type="whatsapp",
            whatsapp_number=None,
        )


def test_order_channels_cod_requires_schema(conn):
    _, store_id, page_id = _seed_landing_page(conn)

    with pytest.raises(DBAPIError):
        _insert_order_channel(
            conn,
            store_id,
            landing_page_id=page_id,
            type="cod",
            whatsapp_number=None,
            cod_form_schema=None,
        )


def test_landing_pages_status_check(conn):
    user_id, store_id = _seed_store(conn)
    category_id = _insert_category(conn)
    concept_id = _insert_product_concept(conn, store_id, user_id, category_id=category_id)
    template_id = _insert_page_template(conn)

    with pytest.raises(DBAPIError):
        _insert_landing_page(conn, store_id, concept_id, template_id, status="live")
