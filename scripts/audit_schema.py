"""Audit the migrated Musawiq schema against the declared schema contract.

Modes:
    --scratch   create a throwaway database from ``MUSAWIQ_ADMIN_DATABASE_URL``,
                run ``alembic upgrade head``, audit, then drop it (default)
    --url DSN   audit an existing migrated database

Checks:
    1. every public base table is declared in ``scripts/schema_manifest.py``
    2. every foreign-key column has an index with that column leading
    3. every append-only table blocks UPDATE/DELETE and has no ``updated_at``
    4. every table with ``store_id`` is classified as tenant or global
    5. no native enum types exist in ``public``
    6. every public base table has a primary key
    7. no two indexes on the same table have an identical definition

The audit is read-only. It prints a readable report by default, emits JSON with
``--json``, and writes ``docs/AUDIT.md`` with ``--write-report``. Exit code is 1
when any check FAILs; SKIPPED does not fail.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit, urlunsplit

import psycopg
from dotenv import load_dotenv

from scripts.schema_manifest import (
    APPEND_ONLY_TABLES,
    GLOBAL_NULLABLE_TENANT_TABLES,
    TABLES,
    TENANT_TABLES,
    TOOL_TABLES,
)

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

REPORT_PATH = ROOT / "docs" / "AUDIT.md"

PASS = "PASS"
FAIL = "FAIL"
SKIPPED = "SKIPPED"


@dataclass
class CheckResult:
    check_id: str
    title: str
    status: str
    reason: str
    details: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.check_id,
            "title": self.title,
            "status": self.status,
            "reason": self.reason,
            "details": self.details,
        }


def libpq_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def with_database(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{database}"))


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def public_tables(conn: psycopg.Connection) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
            ORDER BY c.relname
            """
        )
        return [row[0] for row in cur.fetchall()]


def table_exists(conn: psycopg.Connection, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname = %s
                  AND c.relkind IN ('r', 'p')
            )
            """,
            (table,),
        )
        return bool(cur.fetchone()[0])


def check_tables_declared(conn: psycopg.Connection) -> CheckResult:
    live = set(public_tables(conn)) - TOOL_TABLES
    declared = set(TABLES)
    undeclared = sorted(live - declared)
    missing = sorted(declared - live)
    details = [f"undeclared table: {name}" for name in undeclared]
    details.extend(f"declared table missing: {name}" for name in missing)
    if details:
        return CheckResult(
            "tables_declared",
            "Public tables declared in schema_manifest.py",
            FAIL,
            f"{len(undeclared)} undeclared, {len(missing)} missing",
            details,
        )
    return CheckResult(
        "tables_declared",
        "Public tables declared in schema_manifest.py",
        PASS,
        f"all {len(live)} public tables are declared",
    )


def check_fk_indexes(conn: psycopg.Connection) -> CheckResult:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.relname, a.attname, c.conname
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord)
              ON TRUE
            JOIN pg_attribute a
              ON a.attrelid = c.conrelid AND a.attnum = k.attnum
            WHERE c.contype = 'f'
              AND n.nspname = 'public'
              AND t.relkind IN ('r', 'p')
            ORDER BY t.relname, k.ord, a.attname
            """
        )
        fk_columns = cur.fetchall()

        cur.execute(
            """
            SELECT t.relname, a.attname
            FROM pg_index ix
            JOIN pg_class t ON t.oid = ix.indrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_attribute a
              ON a.attrelid = ix.indrelid AND a.attnum = ix.indkey[0]
            WHERE n.nspname = 'public'
              AND t.relkind IN ('r', 'p')
              AND ix.indisvalid
            """
        )
        indexed = {(table, column) for table, column in cur.fetchall()}

    if not fk_columns:
        return CheckResult(
            "fk_indexes",
            "Foreign-key columns have leading indexes",
            SKIPPED,
            "no foreign-key columns found",
        )

    missing: list[str] = []
    seen: set[tuple[str, str]] = set()
    for table, column, constraint in fk_columns:
        key = (table, column)
        if key in indexed or key in seen:
            continue
        seen.add(key)
        missing.append(f"{table}.{column} (constraint {constraint})")

    if missing:
        return CheckResult(
            "fk_indexes",
            "Foreign-key columns have leading indexes",
            FAIL,
            f"{len(missing)} foreign-key columns lack a leading index",
            missing,
        )
    return CheckResult(
        "fk_indexes",
        "Foreign-key columns have leading indexes",
        PASS,
        f"all {len(set((t, c) for t, c, _ in fk_columns))} foreign-key columns are indexed",
    )


def check_append_only_guards(conn: psycopg.Connection) -> CheckResult:
    details: list[str] = []
    missing_tables: list[str] = []
    for table in sorted(APPEND_ONLY_TABLES):
        if not table_exists(conn, table):
            missing_tables.append(table)
            continue
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = %s
                      AND column_name = 'updated_at'
                )
                """,
                (table,),
            )
            has_updated_at = bool(cur.fetchone()[0])

            cur.execute(
                """
                SELECT tg.tgname, tg.tgtype
                FROM pg_trigger tg
                JOIN pg_class t ON t.oid = tg.tgrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = 'public'
                  AND t.relname = %s
                  AND NOT tg.tgisinternal
                  AND tg.tgenabled <> 'D'
                ORDER BY tg.tgname
                """,
                (table,),
            )
            triggers = cur.fetchall()

        if has_updated_at:
            details.append(f"{table}: append-only table has updated_at column")
        blocking = [
            name
            for name, tgtype in triggers
            if (tgtype & 2) and (tgtype & 8) and (tgtype & 16)
        ]
        if not blocking:
            details.append(
                f"{table}: no BEFORE UPDATE OR DELETE trigger "
                f"(found: {', '.join(name for name, _ in triggers) or 'none'})"
            )

    if details:
        return CheckResult(
            "append_only_guards",
            "Append-only tables block mutation and carry no updated_at",
            FAIL,
            f"{len(details)} append-only violations",
            details,
        )
    if missing_tables:
        return CheckResult(
            "append_only_guards",
            "Append-only tables block mutation and carry no updated_at",
            SKIPPED,
            "table missing: " + ", ".join(missing_tables),
        )
    return CheckResult(
        "append_only_guards",
        "Append-only tables block mutation and carry no updated_at",
        PASS,
        f"all {len(APPEND_ONLY_TABLES)} append-only tables are guarded",
    )


def store_id_tables(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT t.relname
            FROM pg_attribute a
            JOIN pg_class t ON t.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public'
              AND t.relkind IN ('r', 'p')
              AND a.attname = 'store_id'
              AND a.attnum > 0
              AND NOT a.attisdropped
            """
        )
        return {row[0] for row in cur.fetchall()} - TOOL_TABLES


def check_tenant_placement(conn: psycopg.Connection) -> CheckResult:
    classified = set(TENANT_TABLES) | set(GLOBAL_NULLABLE_TENANT_TABLES)
    tenants = store_id_tables(conn)
    if not tenants:
        return CheckResult(
            "tenant_placement",
            "Tables with store_id are classified",
            SKIPPED,
            "no tables with store_id found",
        )
    offending = sorted(tenants - classified)
    if offending:
        return CheckResult(
            "tenant_placement",
            "Tables with store_id are classified",
            FAIL,
            f"{len(offending)} tables with store_id are unclassified",
            [
                f"{table}: store_id present but not in TENANT_TABLES or "
                "GLOBAL_NULLABLE_TENANT_TABLES"
                for table in offending
            ],
        )
    return CheckResult(
        "tenant_placement",
        "Tables with store_id are classified",
        PASS,
        f"all {len(tenants)} tables with store_id are classified",
    )


def check_native_enums(conn: psycopg.Connection) -> CheckResult:
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
        enums = [row[0] for row in cur.fetchall()]
    if enums:
        return CheckResult(
            "native_enums",
            "No native enum types in public",
            FAIL,
            f"{len(enums)} native enum types found",
            [f"native enum: {name}" for name in enums],
        )
    return CheckResult(
        "native_enums",
        "No native enum types in public",
        PASS,
        "no native enum types in public",
    )


def check_primary_keys(conn: psycopg.Connection) -> CheckResult:
    tables = [table for table in public_tables(conn) if table not in TOOL_TABLES]
    if not tables:
        return CheckResult(
            "primary_keys",
            "Every public table has a primary key",
            SKIPPED,
            "no public tables found",
        )
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.relname
            FROM pg_class t
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public'
              AND t.relkind IN ('r', 'p')
              AND NOT EXISTS (
                  SELECT 1 FROM pg_constraint c
                  WHERE c.conrelid = t.oid AND c.contype = 'p'
              )
            ORDER BY t.relname
            """
        )
        missing = [row[0] for row in cur.fetchall() if row[0] not in TOOL_TABLES]
    if missing:
        return CheckResult(
            "primary_keys",
            "Every public table has a primary key",
            FAIL,
            f"{len(missing)} tables have no primary key",
            [f"missing primary key: {table}" for table in missing],
        )
    return CheckResult(
        "primary_keys",
        "Every public table has a primary key",
        PASS,
        f"all {len(tables)} public tables have a primary key",
    )


def index_signature(definition: str) -> str:
    signature = re.sub(
        r"^CREATE (?:UNIQUE )?INDEX \S+ ON (?:ONLY )?",
        "",
        definition,
    )
    return re.sub(r"\s+", " ", signature).strip()


def check_duplicate_indexes(conn: psycopg.Connection) -> CheckResult:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.relname, i.relname, pg_get_indexdef(ix.indexrelid)
            FROM pg_index ix
            JOIN pg_class t ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public'
              AND t.relkind IN ('r', 'p')
            ORDER BY t.relname, i.relname
            """
        )
        rows = cur.fetchall()

    groups: dict[tuple[str, str], list[str]] = {}
    definitions: dict[tuple[str, str], str] = {}
    for table, name, definition in rows:
        signature = index_signature(definition)
        key = (table, signature)
        groups.setdefault(key, []).append(name)
        definitions[key] = signature

    duplicates = [
        (table, definitions[(table, signature)], names)
        for (table, signature), names in sorted(groups.items())
        if len(names) > 1
    ]
    if duplicates:
        details = [
            f"{table}: {', '.join(names)} share {definition}"
            for table, definition, names in duplicates
        ]
        return CheckResult(
            "duplicate_indexes",
            "No duplicate index definitions on a table",
            FAIL,
            f"{len(duplicates)} duplicate index groups",
            details,
        )
    return CheckResult(
        "duplicate_indexes",
        "No duplicate index definitions on a table",
        PASS,
        f"all {len(rows)} indexes have distinct definitions per table",
    )


CHECKS = (
    check_tables_declared,
    check_fk_indexes,
    check_append_only_guards,
    check_tenant_placement,
    check_native_enums,
    check_primary_keys,
    check_duplicate_indexes,
)


def build_report(conn: psycopg.Connection) -> dict[str, object]:
    with conn.cursor() as cur:
        cur.execute("SHOW server_version")
        server_version = cur.fetchone()[0]
    tables = [table for table in public_tables(conn) if table not in TOOL_TABLES]
    results = [check(conn) for check in CHECKS]
    summary = {
        "tables": len(tables),
        PASS: sum(1 for result in results if result.status == PASS),
        FAIL: sum(1 for result in results if result.status == FAIL),
        SKIPPED: sum(1 for result in results if result.status == SKIPPED),
    }
    return {
        "tool": "scripts.audit_schema",
        "postgres_version": server_version,
        "table_names": tables,
        "summary": summary,
        "checks": [result.as_dict() for result in results],
    }


def render_text(report: dict[str, object]) -> str:
    summary = report["summary"]
    lines = [
        "Schema Audit",
        "============",
        f"PostgreSQL: {report['postgres_version']}",
        f"Tables: {summary['tables']}",
        "",
    ]
    for check in report["checks"]:
        lines.append(f"[{check['status']}] {check['title']} ({check['id']})")
        lines.append(f"    {check['reason']}")
        for detail in check["details"]:
            lines.append(f"    - {detail}")
    lines.extend(
        [
            "",
            f"Summary: {summary[PASS]} passed, {summary[FAIL]} failed, "
            f"{summary[SKIPPED]} skipped",
            "AUDIT OK" if summary[FAIL] == 0 else "AUDIT FAILED",
        ]
    )
    return "\n".join(lines) + "\n"


def render_markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    lines = [
        "# Schema Audit",
        "",
        "Generated by `scripts/audit_schema.py` from a database migrated to "
        "`alembic upgrade head`. Regenerate with:",
        "",
        "```",
        "python -m scripts.audit_schema --scratch --write-report",
        "```",
        "",
        f"- PostgreSQL: {report['postgres_version']}",
        f"- Tables: {summary['tables']}",
        f"- Checks: {summary[PASS]} passed, {summary[FAIL]} failed, "
        f"{summary[SKIPPED]} skipped",
        "- Verdict: " + ("PASS" if summary[FAIL] == 0 else "FAIL"),
        "",
        "## Checks",
        "",
    ]
    for check in report["checks"]:
        lines.append(f"### {check['status']} - {check['title']}")
        lines.append("")
        lines.append(f"Check id: `{check['id']}`")
        lines.append("")
        lines.append(check["reason"])
        if check["details"]:
            lines.append("")
            lines.extend(f"- {detail}" for detail in check["details"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_markdown(report: dict[str, object], path: Path = REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8", newline="\n")


def audit_url(url: str) -> dict[str, object]:
    conn = psycopg.connect(libpq_url(url))
    try:
        conn.read_only = True
        return build_report(conn)
    finally:
        conn.close()


@contextmanager
def scratch_database(
    prefix: str = "musawiq_audit", quiet: bool = False
) -> Iterator[str]:
    admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
    if not admin_url:
        raise RuntimeError("MUSAWIQ_ADMIN_DATABASE_URL is not set")

    scratch = f"{prefix}_{uuid.uuid4().hex[:10]}"
    admin = psycopg.connect(libpq_url(admin_url), autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(f"CREATE DATABASE {quote_ident(scratch)}")
        if not quiet:
            print(f"created scratch database: {scratch}", file=sys.stderr)

        url = with_database(admin_url, scratch)
        env = os.environ.copy()
        env["MUSAWIQ_DATABASE_URL"] = url
        process = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            env=env,
            capture_output=quiet,
            text=True,
        )
        if process.returncode != 0:
            output = (process.stderr or process.stdout or "").strip()
            raise RuntimeError(f"alembic upgrade head failed: {output}")
        yield url
    finally:
        try:
            with admin.cursor() as cur:
                cur.execute(
                    f"DROP DATABASE IF EXISTS {quote_ident(scratch)} WITH (FORCE)"
                )
            if not quiet:
                print(f"dropped scratch database: {scratch}", file=sys.stderr)
        finally:
            admin.close()


def report_exit_code(report: dict[str, object]) -> int:
    return 1 if report["summary"][FAIL] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--scratch",
        action="store_true",
        help="create a throwaway database from MUSAWIQ_ADMIN_DATABASE_URL (default)",
    )
    group.add_argument("--url", help="audit an existing migrated database")
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a machine-readable JSON report to stdout",
    )
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="write the markdown report to docs/AUDIT.md",
    )
    args = parser.parse_args(argv)

    try:
        if args.url:
            report = audit_url(args.url)
        else:
            with scratch_database(quiet=args.json) as url:
                report = audit_url(url)
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.write_report:
        write_markdown(report)
        print(f"wrote {REPORT_PATH.relative_to(ROOT)}", file=sys.stderr)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_text(report), end="")

    return report_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
