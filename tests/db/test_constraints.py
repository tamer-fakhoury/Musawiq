"""Structural invariants that hold for every migration state."""

from __future__ import annotations

from sqlalchemy import text


def test_no_native_enums(conn):
    rows = conn.execute(
        text(
            """
            SELECT t.typname
            FROM pg_type t
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE t.typtype = 'e' AND n.nspname = 'public'
            """
        )
    ).scalars().all()
    assert rows == [], f"native ENUM types are forbidden: {rows}"


def test_every_public_table_has_primary_key(conn):
    rows = conn.execute(
        text(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_constraint p
              ON p.conrelid = c.oid AND p.contype = 'p'
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND c.relname NOT IN ('schema_migrations', 'alembic_version')
              AND p.oid IS NULL
            """
        )
    ).scalars().all()
    assert rows == [], f"tables without a primary key: {rows}"


def test_uuid_id_columns_have_default(conn):
    rows = conn.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND column_name = 'id'
              AND udt_name = 'uuid'
              AND column_default IS NULL
            """
        )
    ).scalars().all()
    assert rows == [], f"uuid id columns missing a default: {rows}"
