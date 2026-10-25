"""Foreign-key matrix and deferred-reference worklist (DB-0.13).

Modes:
    --scratch   create a throwaway database from ``MUSAWIQ_ADMIN_DATABASE_URL``,
                run ``alembic upgrade head``, introspect, then drop it (default)
    --url DSN   introspect an existing migrated database

Output:
    (default)        print the Markdown report
    --json           print the matrix as JSON
    --write-report   write docs/FK-MATRIX.md
    --check          compare docs/FK-MATRIX.md and exit 1 on drift

The deferred worklist contains only columns that end in ``_id``/``_by``, have no
resolved FK, have a UUID type, and whose plausible target table actually exists.
Polymorphic references, array columns, external identifiers, and client-generated
idempotency keys are excluded and reported separately.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from scripts.gen_schema_docs import (
    ROOT,
    TOOL_TABLES,
    Column,
    Table,
    display_path,
    fetch_columns,
    fetch_tables,
    first_difference,
    libpq_url,
    quote_ident,
    with_database,
)

load_dotenv(ROOT / ".env")

DEFAULT_OUTPUT = ROOT / "docs" / "FK-MATRIX.md"

ACTION_NAMES = {
    "a": "NO ACTION",
    "r": "RESTRICT",
    "c": "CASCADE",
    "n": "SET NULL",
    "d": "SET DEFAULT",
}

POLYMORPHIC_EXCEPTIONS: dict[tuple[str, str], str] = {
    ("audit_logs", "target_id"): "polymorphic target reference",
    ("attributions", "subject_id"): "polymorphic subject reference",
    ("alerts", "related_id"): "polymorphic related reference",
}

NON_FK_IDENTIFIERS: dict[tuple[str, str], str] = {
    ("events", "event_id"): "client-generated idempotency key",
}

# Irregular or ambiguous singular column stems. Everything else falls back to
# naive pluralisation (campaign -> campaigns, ad_variation -> ad_variations).
TARGET_OVERRIDES: dict[str, str] = {
    "adset_id": "ad_sets",
    "rule_set_id": "optimization_rule_sets",
    "decision_rule_set_id": "decision_rule_sets",
    "template_id": "page_templates",
    "source_idea_id": "product_ideas",
    "converted_concept_id": "product_concepts",
    "created_order_id": "orders",
    "current_version_id": "page_versions",
    "published_version_id": "page_versions",
    "result_snapshot_id": "test_result_snapshots",
    "finding_id": "performance_findings",
    "recommendation_id": "optimization_recommendations",
    "investment_profile_id": "investment_profiles",
    "investment_recommendation_id": "investment_recommendations",
}


@dataclass(frozen=True)
class ResolvedFK:
    child_table: str
    child_columns: tuple[str, ...]
    parent_table: str
    parent_columns: tuple[str, ...]
    constraint: str
    on_delete: str
    on_update: str
    deferrable: bool
    initially_deferred: bool


@dataclass(frozen=True)
class DeferredCandidate:
    table: str
    column: str
    type: str
    target_table: str


@dataclass(frozen=True)
class ExcludedColumn:
    table: str
    column: str
    type: str
    reason: str


@dataclass(frozen=True)
class Matrix:
    application_tables: tuple[str, ...]
    resolved: tuple[ResolvedFK, ...]
    candidates: tuple[DeferredCandidate, ...]
    polymorphic: tuple[ExcludedColumn, ...]
    arrays: tuple[ExcludedColumn, ...]
    non_fk_identifiers: tuple[ExcludedColumn, ...]
    tables_without_outbound_fk: tuple[str, ...]
    tables_without_inbound_fk: tuple[str, ...]
    tables_without_any_fk: tuple[str, ...]


def pluralize(stem: str) -> str:
    if len(stem) > 1 and stem.endswith("y") and stem[-2] not in "aeiou":
        return stem[:-1] + "ies"
    return stem + "s"


def infer_target(table_name: str, column: Column) -> str | None:
    name = column.name.lower()
    if column.type != "uuid":
        return None
    if name.endswith("_by"):
        return "users"
    if not name.endswith("_id"):
        return None
    if name == "parent_id":
        return table_name
    if name.endswith("_user_id"):
        return "users"
    if name.endswith("_file_id"):
        return "stored_files"
    if name in TARGET_OVERRIDES:
        return TARGET_OVERRIDES[name]
    return pluralize(name[:-3])


def fetch_resolved_fks(conn: psycopg.Connection) -> tuple[ResolvedFK, ...]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT con.conname,
                   child.relname AS child_table,
                   parent.relname AS parent_table,
                   ARRAY(
                       SELECT a.attname
                       FROM unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
                       JOIN pg_attribute a
                         ON a.attrelid = con.conrelid AND a.attnum = k.attnum
                       ORDER BY k.ord
                   ) AS child_columns,
                   ARRAY(
                       SELECT a.attname
                       FROM unnest(con.confkey) WITH ORDINALITY AS k(attnum, ord)
                       JOIN pg_attribute a
                         ON a.attrelid = con.confrelid AND a.attnum = k.attnum
                       ORDER BY k.ord
                   ) AS parent_columns,
                   con.confdeltype,
                   con.confupdtype,
                   con.condeferrable,
                   con.condeferred
            FROM pg_constraint con
            JOIN pg_class child ON child.oid = con.conrelid
            JOIN pg_class parent ON parent.oid = con.confrelid
            JOIN pg_namespace n ON n.oid = child.relnamespace
            WHERE con.contype = 'f' AND n.nspname = 'public'
            ORDER BY child.relname, con.conname
            """
        )
        resolved = []
        for (
            constraint,
            child_table,
            parent_table,
            child_columns,
            parent_columns,
            delete_action,
            update_action,
            deferrable,
            initially_deferred,
        ) in cur.fetchall():
            resolved.append(
                ResolvedFK(
                    child_table=child_table,
                    child_columns=tuple(child_columns),
                    parent_table=parent_table,
                    parent_columns=tuple(parent_columns),
                    constraint=constraint,
                    on_delete=ACTION_NAMES.get(delete_action, delete_action),
                    on_update=ACTION_NAMES.get(update_action, update_action),
                    deferrable=bool(deferrable),
                    initially_deferred=bool(initially_deferred),
                )
            )
    return tuple(resolved)


def build_matrix(conn: psycopg.Connection) -> Matrix:
    application_tables = tuple(
        table for table in fetch_tables(conn) if table not in TOOL_TABLES
    )
    application_set = set(application_tables)
    columns_by_table = {
        table: fetch_columns(conn, table) for table in application_tables
    }
    resolved = fetch_resolved_fks(conn)
    resolved_columns = {
        (fk.child_table, column)
        for fk in resolved
        for column in fk.child_columns
    }

    candidates: list[DeferredCandidate] = []
    polymorphic: list[ExcludedColumn] = []
    arrays: list[ExcludedColumn] = []
    non_fk_identifiers: list[ExcludedColumn] = []

    for table in application_tables:
        for column in columns_by_table[table]:
            key = (table, column.name)
            if key in resolved_columns:
                continue
            if column.type.endswith("[]"):
                arrays.append(
                    ExcludedColumn(table, column.name, column.type, "array column")
                )
                continue
            if key in POLYMORPHIC_EXCEPTIONS:
                polymorphic.append(
                    ExcludedColumn(
                        table,
                        column.name,
                        column.type,
                        POLYMORPHIC_EXCEPTIONS[key],
                    )
                )
                continue
            if key in NON_FK_IDENTIFIERS:
                non_fk_identifiers.append(
                    ExcludedColumn(
                        table,
                        column.name,
                        column.type,
                        NON_FK_IDENTIFIERS[key],
                    )
                )
                continue
            if not (column.name.endswith("_id") or column.name.endswith("_by")):
                continue
            target = infer_target(table, column)
            if target is None:
                reason = (
                    "non-UUID identifier"
                    if column.type != "uuid"
                    else "no plausible target table"
                )
                non_fk_identifiers.append(
                    ExcludedColumn(table, column.name, column.type, reason)
                )
                continue
            if target not in application_set:
                non_fk_identifiers.append(
                    ExcludedColumn(
                        table,
                        column.name,
                        column.type,
                        f"target table {target} is not present",
                    )
                )
                continue
            candidates.append(
                DeferredCandidate(
                    table=table,
                    column=column.name,
                    type=column.type,
                    target_table=target,
                )
            )

    candidates.sort(key=lambda item: (item.table, item.column))
    polymorphic.sort(key=lambda item: (item.table, item.column))
    arrays.sort(key=lambda item: (item.table, item.column))
    non_fk_identifiers.sort(key=lambda item: (item.table, item.column))

    outbound = {fk.child_table for fk in resolved}
    inbound = {fk.parent_table for fk in resolved}
    tables_without_outbound = tuple(
        table for table in application_tables if table not in outbound
    )
    tables_without_inbound = tuple(
        table for table in application_tables if table not in inbound
    )
    tables_without_any = tuple(
        table
        for table in application_tables
        if table not in outbound and table not in inbound
    )

    return Matrix(
        application_tables=application_tables,
        resolved=resolved,
        candidates=tuple(candidates),
        polymorphic=tuple(polymorphic),
        arrays=tuple(arrays),
        non_fk_identifiers=tuple(non_fk_identifiers),
        tables_without_outbound_fk=tables_without_outbound,
        tables_without_inbound_fk=tables_without_inbound,
        tables_without_any_fk=tables_without_any,
    )


def format_columns(columns: tuple[str, ...]) -> str:
    return ", ".join(f"`{column}`" for column in columns)


def deferrable_label(fk: ResolvedFK) -> str:
    if not fk.deferrable:
        return "no"
    if fk.initially_deferred:
        return "yes (initially deferred)"
    return "yes"


def markdown_list(values: tuple[str, ...]) -> list[str]:
    if not values:
        return ["- _None._"]
    return [f"- `{value}`" for value in values]


def render_report(matrix: Matrix) -> str:
    lines = [
        "# Foreign-Key Matrix (DB-0.13)",
        "",
        "Generated by `scripts/fk_matrix.py` from the migrated schema. Do not edit "
        "this file by hand; regenerate it.",
        "",
        "## Summary",
        "",
        f"- Application tables: {len(matrix.application_tables)}",
        f"- Resolved FKs: {len(matrix.resolved)}",
        f"- Deferred candidates: {len(matrix.candidates)}",
        f"- Tables with no outbound FK: {len(matrix.tables_without_outbound_fk)}",
        f"- Tables with no inbound FK: {len(matrix.tables_without_inbound_fk)}",
        f"- Tables with no FK at all: {len(matrix.tables_without_any_fk)}",
        "",
        "Tool tables (`schema_migrations`, `alembic_version`) are excluded from the "
        "table counts.",
        "",
        "## Tables with no outbound FK",
        "",
    ]
    lines.extend(markdown_list(matrix.tables_without_outbound_fk))
    lines.extend(["", "## Tables with no inbound FK", ""])
    lines.extend(markdown_list(matrix.tables_without_inbound_fk))
    lines.extend(["", "## Tables with no FK at all", ""])
    lines.extend(markdown_list(matrix.tables_without_any_fk))

    lines.extend(
        [
            "",
            "## Resolved foreign keys",
            "",
            "| Child table | Child columns | Parent table | Parent columns | "
            "Constraint | ON DELETE | ON UPDATE | Deferrable |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for fk in matrix.resolved:
        lines.append(
            f"| `{fk.child_table}` | {format_columns(fk.child_columns)} | "
            f"`{fk.parent_table}` | {format_columns(fk.parent_columns)} | "
            f"`{fk.constraint}` | {fk.on_delete} | {fk.on_update} | "
            f"{deferrable_label(fk)} |"
        )
    if not matrix.resolved:
        lines.append("| _None._ |  |  |  |  |  |  |  |")

    lines.extend(
        [
            "",
            "## Deferred candidates",
            "",
            "These columns have no FK constraint, have a UUID type, and their "
            "inferred target table exists. They are the worklist for DB-0.13.",
            "",
            "| Child table | Column | Type | Inferred target table |",
            "| --- | --- | --- | --- |",
        ]
    )
    for candidate in matrix.candidates:
        lines.append(
            f"| `{candidate.table}` | `{candidate.column}` | "
            f"`{candidate.type}` | `{candidate.target_table}` |"
        )
    if not matrix.candidates:
        lines.append("| _None._ |  |  |  |")

    lines.extend(
        [
            "",
            "## Excluded from the worklist",
            "",
            "### Polymorphic references",
            "",
            "| Column | Reason |",
            "| --- | --- |",
        ]
    )
    for item in matrix.polymorphic:
        lines.append(f"| `{item.table}.{item.column}` | {item.reason} |")
    if not matrix.polymorphic:
        lines.append("| _None._ |  |")

    lines.extend(
        [
            "",
            "### Array columns",
            "",
            "| Column | Type | Reason |",
            "| --- | --- | --- |",
        ]
    )
    for item in matrix.arrays:
        lines.append(
            f"| `{item.table}.{item.column}` | `{item.type}` | {item.reason} |"
        )
    if not matrix.arrays:
        lines.append("| _None._ |  |  |")

    lines.extend(
        [
            "",
            "### Non-FK identifiers",
            "",
            "| Column | Type | Reason |",
            "| --- | --- | --- |",
        ]
    )
    for item in matrix.non_fk_identifiers:
        lines.append(
            f"| `{item.table}.{item.column}` | `{item.type}` | {item.reason} |"
        )
    if not matrix.non_fk_identifiers:
        lines.append("| _None._ |  |  |")

    lines.extend(
        [
            "",
            "## Rules",
            "",
            "- A resolved FK is any `pg_constraint` row with `contype = 'f'` in "
            "`public`.",
            "- A deferred candidate must be a UUID `_id`/`_by` column with no "
            "resolved FK and a target table that exists in this schema.",
            "- Polymorphic references, array columns, external identifiers, "
            "correlation IDs, and `events.event_id` are never candidates.",
            "- A missing target table means no candidate is invented; it is listed "
            "under non-FK identifiers with the reason.",
            "",
        ]
    )
    return "\n".join(lines)


def matrix_to_dict(matrix: Matrix) -> dict:
    return {
        "summary": {
            "application_tables": len(matrix.application_tables),
            "resolved_fks": len(matrix.resolved),
            "deferred_candidates": len(matrix.candidates),
            "tables_without_outbound_fk": len(matrix.tables_without_outbound_fk),
            "tables_without_inbound_fk": len(matrix.tables_without_inbound_fk),
            "tables_without_any_fk": len(matrix.tables_without_any_fk),
        },
        "resolved": [asdict(item) for item in matrix.resolved],
        "deferred": [asdict(item) for item in matrix.candidates],
        "excluded": {
            "polymorphic": [asdict(item) for item in matrix.polymorphic],
            "arrays": [asdict(item) for item in matrix.arrays],
            "non_fk_identifiers": [
                asdict(item) for item in matrix.non_fk_identifiers
            ],
        },
        "tables_without_outbound_fk": list(matrix.tables_without_outbound_fk),
        "tables_without_inbound_fk": list(matrix.tables_without_inbound_fk),
        "tables_without_any_fk": list(matrix.tables_without_any_fk),
    }


def write_report(document: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="\n")


def check_report(document: str, output: Path) -> int:
    display = display_path(output)
    if not output.exists():
        print(f"FK MATRIX DRIFT: {display} does not exist", file=sys.stderr)
        return 1

    expected_bytes = output.read_bytes()
    generated_bytes = document.encode("utf-8")
    if expected_bytes == generated_bytes:
        print(f"FK MATRIX OK: {display} is in sync")
        return 0

    expected = expected_bytes.decode("utf-8", errors="replace")
    generated = generated_bytes.decode("utf-8", errors="replace")
    line, section, expected_line, generated_line = first_difference(
        expected, generated
    )
    print(f"FK MATRIX DRIFT: {display} is out of date", file=sys.stderr)
    print(f"  first differing section: {section}", file=sys.stderr)
    if line:
        print(f"  first differing line: {line}", file=sys.stderr)
        print(f"  committed: {expected_line!r}", file=sys.stderr)
        print(f"  generated: {generated_line!r}", file=sys.stderr)
    else:
        print("  byte-level difference; line content is equal", file=sys.stderr)
    return 1


@contextmanager
def scratch_database(admin_url: str) -> Iterator[str]:
    scratch = f"musawiq_fk_matrix_{uuid.uuid4().hex[:10]}"
    scratch_url = with_database(admin_url, scratch)
    admin = psycopg.connect(libpq_url(admin_url), autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(f"CREATE DATABASE {quote_ident(scratch)}")
        print(f"created scratch database: {scratch}", file=sys.stderr)

        env = os.environ.copy()
        env["MUSAWIQ_DATABASE_URL"] = scratch_url
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            env=env,
            check=True,
        )
        yield scratch_url
    finally:
        with admin.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {quote_ident(scratch)} WITH (FORCE)")
        admin.close()
        print(f"dropped scratch database: {scratch}", file=sys.stderr)


def matrix_for_url(url: str) -> Matrix:
    with psycopg.connect(libpq_url(url)) as conn:
        return build_matrix(conn)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--scratch",
        action="store_true",
        help="create a throwaway database from MUSAWIQ_ADMIN_DATABASE_URL (default)",
    )
    group.add_argument(
        "--url",
        help="introspect an existing migrated database instead of creating a scratch one",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--json",
        action="store_true",
        help="print the matrix as JSON",
    )
    mode.add_argument(
        "--write-report",
        action="store_true",
        help="write the Markdown report",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="compare with the report and exit 1 on drift",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="report path (default: docs/FK-MATRIX.md)",
    )
    args = parser.parse_args(argv)

    output = args.output if args.output.is_absolute() else ROOT / args.output
    try:
        if args.url:
            matrix = matrix_for_url(args.url)
        else:
            admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
            if not admin_url:
                print(
                    "FAIL: MUSAWIQ_ADMIN_DATABASE_URL is not set",
                    file=sys.stderr,
                )
                return 1
            with scratch_database(admin_url) as url:
                matrix = matrix_for_url(url)
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    report = render_report(matrix)
    if args.json:
        print(json.dumps(matrix_to_dict(matrix), indent=2, sort_keys=True))
        return 0
    if args.write_report:
        write_report(report, output)
        print(f"wrote {display_path(output)}")
        return 0
    if args.check:
        return check_report(report, output)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
