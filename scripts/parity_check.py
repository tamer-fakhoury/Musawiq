"""Compare the live database schema against ``scripts/schema_manifest.py``.

Exit code 0 = parity, 1 = drift. Run standalone or via ``scripts/verify_db.py``.

This does not parse ``docs/Specifications.md`` at runtime; the manifest is the
machine-checkable projection of it, and keeping the two in sync is part of each
DB task's Definition of Done.
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg

from scripts.schema_manifest import (
    APPEND_ONLY_TABLES,
    TABLES,
    TOOL_TABLES,
)

TYPE_MAP = {
    "uuid": "uuid",
    "text": "text",
    "character varying": "text",
    "character": "text",
    "citext": "text",
    "bigint": "bigint",
    "integer": "integer",
    "smallint": "integer",
    "boolean": "boolean",
    "timestamp with time zone": "timestamptz",
    "timestamp without time zone": "timestamptz",
    "date": "date",
    "jsonb": "jsonb",
    "json": "jsonb",
    "bytea": "bytea",
    "numeric": "numeric",
    "inet": "inet",
    "ARRAY": "array",
}


def libpq_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def _coarse_type(data_type: str, udt_name: str) -> str:
    if data_type == "ARRAY":
        return "array"
    if data_type in ("USER-DEFINED", "CHARACTER VARYING"):
        if udt_name == "citext":
            return "text"
    return TYPE_MAP.get(data_type, TYPE_MAP.get(udt_name, data_type.lower()))


def live_schema(conn: psycopg.Connection) -> dict[str, dict[str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name, column_name, data_type, udt_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
            """
        )
        out: dict[str, dict[str, str]] = {}
        for table, column, data_type, udt_name in cur.fetchall():
            out.setdefault(table, {})[column] = _coarse_type(data_type, udt_name)
    return out


def native_enums(conn: psycopg.Connection) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.typname
            FROM pg_type t
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE t.typtype = 'e' AND n.nspname = 'public'
            ORDER BY t.typname
            """
        )
        return [row[0] for row in cur.fetchall()]


def missing_updatable_version(conn: psycopg.Connection) -> list[str]:
    """Append-only tables must not carry updated_at."""
    findings: list[str] = []
    live = live_schema(conn)
    for table in APPEND_ONLY_TABLES:
        if table in live and "updated_at" in live[table]:
            findings.append(f"{table}: append-only table has updated_at")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("MUSAWIQ_TEST_DATABASE_URL"))
    args = parser.parse_args(argv)

    if not args.url:
        print("FAIL: MUSAWIQ_TEST_DATABASE_URL is not set", file=sys.stderr)
        return 1

    problems: list[str] = []

    with psycopg.connect(libpq_url(args.url)) as conn:
        live = live_schema(conn)

        for enum_name in native_enums(conn):
            problems.append(f"native ENUM type not allowed: {enum_name}")

        for table, columns in TABLES.items():
            if table not in live:
                problems.append(f"missing table: {table}")
                continue
            for name, expected in columns:
                actual = live[table].get(name)
                if actual is None:
                    problems.append(f"missing column: {table}.{name}")
                elif actual != expected:
                    problems.append(
                        f"type drift: {table}.{name} expected {expected}, got {actual}"
                    )

        unexpected = set(live) - set(TABLES) - TOOL_TABLES
        for table in sorted(unexpected):
            problems.append(f"undeclared table: {table}")

        problems.extend(missing_updatable_version(conn))

    if problems:
        print("PARITY FAILED")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"PARITY OK ({len(TABLES)} declared tables)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
