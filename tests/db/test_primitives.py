"""Shared primitives: native uuidv7 and the trigger functions from DB-0.2."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def test_uuidv7_is_native_and_version_seven(conn):
    version = conn.execute(text("SELECT uuid_extract_version(uuidv7())")).scalar_one()
    shim = conn.execute(
        text(
            """
            SELECT count(*)
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' AND p.proname = 'uuidv7'
            """
        )
    ).scalar_one()

    assert version == 7
    assert shim == 0


def test_touch_updated_at_sets_now(conn):
    conn.execute(
        text(
            """
            CREATE TEMPORARY TABLE tmp_touch_updated_at (
                id integer PRIMARY KEY,
                updated_at timestamptz NOT NULL
            ) ON COMMIT DROP
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TRIGGER trg_tmp_touch_updated_at
            BEFORE UPDATE ON tmp_touch_updated_at
            FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
            """
        )
    )
    conn.execute(
        text(
            """
            INSERT INTO tmp_touch_updated_at (id, updated_at)
            VALUES (1, '2000-01-01T00:00:00Z')
            """
        )
    )
    conn.execute(
        text(
            """
            UPDATE tmp_touch_updated_at
            SET updated_at = '2000-01-01T00:00:00Z'
            WHERE id = 1
            """
        )
    )

    updated_at = conn.execute(
        text("SELECT updated_at FROM tmp_touch_updated_at WHERE id = 1")
    ).scalar_one()

    assert updated_at > datetime(2000, 1, 1, tzinfo=timezone.utc)


def _create_append_only_probe(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TEMPORARY TABLE tmp_append_only (
                id integer PRIMARY KEY,
                value text
            ) ON COMMIT DROP
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TRIGGER trg_tmp_append_only_block_mutation
            BEFORE UPDATE OR DELETE ON tmp_append_only
            FOR EACH ROW EXECUTE FUNCTION fn_block_mutation()
            """
        )
    )
    conn.execute(
        text("INSERT INTO tmp_append_only (id, value) VALUES (1, 'original')")
    )


def test_block_mutation_rejects_update(conn):
    _create_append_only_probe(conn)

    with pytest.raises(DBAPIError, match="append-only"):
        conn.execute(
            text("UPDATE tmp_append_only SET value = 'changed' WHERE id = 1")
        )


def test_block_mutation_rejects_delete(conn):
    _create_append_only_probe(conn)

    with pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text("DELETE FROM tmp_append_only WHERE id = 1"))
