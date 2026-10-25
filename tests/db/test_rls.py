"""Row-level security invariants.

Skipped until DB-0.15 lands. Run with ``--expect-rls`` on verify_db to enable.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.getenv("MUSAWIQ_EXPECT_RLS") != "1",
    reason="RLS not enabled yet (DB-0.15)",
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
              AND c.relrowsecurity = false
            """
        )
    ).scalars().all()
    assert rows == [], f"tenant tables missing RLS: {rows}"


def test_platform_global_tables_have_rls(conn):
    """Tables with a nullable store_id still need a tenant policy."""
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
              AND c.relrowsecurity = false
            """
        )
    ).scalars().all()
    assert rows == [], f"global tables missing RLS: {rows}"
