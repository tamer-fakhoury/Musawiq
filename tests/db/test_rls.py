"""Row-level security invariants and tenant isolation.

Skipped unless ``scripts.verify_db --expect-rls`` sets ``MUSAWIQ_EXPECT_RLS``.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.getenv("MUSAWIQ_EXPECT_RLS") != "1",
    reason="RLS tests require scripts.verify_db --expect-rls",
)


def _set_setting(conn, name: str, value) -> None:
    conn.execute(
        text("SELECT set_config(:name, :value, true)"),
        {"name": name, "value": "" if value is None else str(value)},
    )


def test_tenant_tables_have_rls(conn):
    rows = conn.execute(
        text(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN information_schema.columns col
              ON col.table_schema = 'public'
             AND col.table_name = c.relname
             AND col.column_name = 'store_id'
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND col.is_nullable = 'NO'
              AND (c.relrowsecurity = false OR c.relforcerowsecurity = false)
            ORDER BY c.relname
            """
        )
    ).scalars().all()
    assert rows == [], f"tenant tables missing RLS/FORCE: {rows}"


def test_platform_global_tables_have_rls(conn):
    """Tables with a nullable store_id still need forced RLS."""
    rows = conn.execute(
        text(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN information_schema.columns col
              ON col.table_schema = 'public'
             AND col.table_name = c.relname
             AND col.column_name = 'store_id'
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND col.is_nullable = 'YES'
              AND (c.relrowsecurity = false OR c.relforcerowsecurity = false)
            ORDER BY c.relname
            """
        )
    ).scalars().all()
    assert rows == [], f"global tables missing RLS/FORCE: {rows}"


def test_stores_and_users_have_rls(conn):
    rows = conn.execute(
        text(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND c.relname IN ('stores', 'users')
              AND (c.relrowsecurity = false OR c.relforcerowsecurity = false)
            ORDER BY c.relname
            """
        )
    ).scalars().all()
    assert rows == [], f"stores/users missing RLS/FORCE: {rows}"


def test_rls_isolates_tenants(app_conn):
    conn = app_conn
    user_a = uuid.uuid4()
    store_a = uuid.uuid4()
    user_b = uuid.uuid4()
    store_b = uuid.uuid4()

    _set_setting(conn, "app.user_id", user_a)
    conn.execute(
        text(
            """
            INSERT INTO users (id, email, full_name, role, status)
            VALUES (:id, 'rls-a@example.com', 'RLS A', 'owner', 'active')
            """
        ),
        {"id": user_a},
    )

    _set_setting(conn, "app.store_id", store_a)
    conn.execute(
        text(
            """
            INSERT INTO stores (
                id, owner_user_id, name, slug, status,
                default_currency, default_language, timezone, country_code,
                onboarding_status
            )
            VALUES (
                :id, :owner_user_id, 'Store A', 'rls-store-a', 'active',
                'USD', 'en', 'UTC', 'US', 'completed'
            )
            """
        ),
        {"id": store_a, "owner_user_id": user_a},
    )

    _set_setting(conn, "app.user_id", user_b)
    conn.execute(
        text(
            """
            INSERT INTO users (id, email, full_name, role, status)
            VALUES (:id, 'rls-b@example.com', 'RLS B', 'owner', 'active')
            """
        ),
        {"id": user_b},
    )

    _set_setting(conn, "app.store_id", store_b)
    conn.execute(
        text(
            """
            INSERT INTO stores (
                id, owner_user_id, name, slug, status,
                default_currency, default_language, timezone, country_code,
                onboarding_status
            )
            VALUES (
                :id, :owner_user_id, 'Store B', 'rls-store-b', 'active',
                'USD', 'en', 'UTC', 'US', 'completed'
            )
            """
        ),
        {"id": store_b, "owner_user_id": user_b},
    )

    _set_setting(conn, "app.store_id", store_a)
    product_a = conn.execute(
        text(
            """
            INSERT INTO products (store_id, name, currency, source)
            VALUES (:store_id, 'Product A', 'USD', 'manual')
            RETURNING id
            """
        ),
        {"store_id": store_a},
    ).scalar_one()

    _set_setting(conn, "app.store_id", store_b)
    product_b = conn.execute(
        text(
            """
            INSERT INTO products (store_id, name, currency, source)
            VALUES (:store_id, 'Product B', 'USD', 'manual')
            RETURNING id
            """
        ),
        {"store_id": store_b},
    ).scalar_one()

    _set_setting(conn, "app.store_id", store_a)
    visible = set(conn.execute(text("SELECT id FROM products")).scalars().all())
    assert visible == {product_a}

    _set_setting(conn, "app.store_id", None)
    count = conn.execute(text("SELECT count(*) FROM products")).scalar_one()
    assert count == 0

    _set_setting(conn, "app.store_id", store_a)
    result = conn.execute(
        text("UPDATE products SET name = 'hacked' WHERE id = :id"),
        {"id": product_b},
    )
    assert result.rowcount == 0

    _set_setting(conn, "app.store_id", store_b)
    name_b = conn.execute(
        text("SELECT name FROM products WHERE id = :id"),
        {"id": product_b},
    ).scalar_one()
    assert name_b == "Product B"
