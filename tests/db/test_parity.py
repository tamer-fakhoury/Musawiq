"""Schema parity between the live database and the declared manifest."""

from __future__ import annotations

import psycopg
import pytest

from scripts.parity_check import libpq_url, main as parity_main


def test_manifest_matches_database(db_url):
    assert parity_main(["--url", db_url]) == 0


def test_no_undeclared_tables(db_url, engine):
    from scripts.schema_manifest import TABLES, TOOL_TABLES

    from sqlalchemy import text

    with engine.connect() as connection:
        live = set(
            connection.execute(
                text(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                    """
                )
            ).scalars()
        )
    assert live - set(TABLES) - TOOL_TABLES == set()
