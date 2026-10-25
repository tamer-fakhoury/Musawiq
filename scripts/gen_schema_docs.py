"""Generate ``docs/SCHEMA.md`` from a migrated Musawiq database.

Modes:
    --scratch   create a throwaway database from ``MUSAWIQ_ADMIN_DATABASE_URL``,
                run ``alembic upgrade head``, introspect, then drop it (default)
    --url DSN   introspect an existing migrated database

The document is deterministic: tables, constraints, and indexes are emitted in
sorted order, and no timestamps, database names, or credentials are embedded.
Exit code is non-zero if migration or introspection fails.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DEFAULT_OUTPUT = ROOT / "docs" / "SCHEMA.md"

# Physical table -> entity in docs/Specifications.md (## Entity Fields).
# Reference data keeps natural primary keys; every other entity is pluralised.
ENTITY_BY_TABLE: dict[str, str] = {
    "ad_account_connections": "AdAccountConnection",
    "ad_platforms": "AdPlatform",
    "ad_sets": "AdSet",
    "ad_variations": "AdVariation",
    "alerts": "Alert",
    "async_jobs": "AsyncJob",
    "attributions": "Attribution",
    "audience_profiles": "AudienceProfile",
    "audience_segments": "AudienceSegment",
    "audit_logs": "AuditLog",
    "budget_policies": "BudgetPolicy",
    "campaigns": "Campaign",
    "categories": "Category",
    "column_mappings": "ColumnMapping",
    "content_generation_jobs": "ContentGenerationJob",
    "content_providers": "ContentProvider",
    "countries": "Country",
    "creative_variants": "CreativeVariant",
    "creatives": "Creative",
    "currencies": "Currency",
    "decision_rule_sets": "DecisionRuleSet",
    "demand_estimates": "DemandEstimate",
    "deposits": "Deposit",
    "evaluations": "Evaluation",
    "event_types": "EventType",
    "events": "Event",
    "feedback_items": "FeedbackItem",
    "generation_runs": "GenerationRun",
    "idea_evidence": "IdeaEvidence",
    "import_batches": "ImportBatch",
    "import_issues": "ImportIssue",
    "import_rows": "ImportRow",
    "investment_profiles": "InvestmentProfile",
    "investment_recommendations": "InvestmentRecommendation",
    "landing_pages": "LandingPage",
    "languages": "Language",
    "metric_snapshots": "MetricSnapshot",
    "niches": "Niche",
    "optimization_actions": "OptimizationAction",
    "optimization_recommendations": "OptimizationRecommendation",
    "optimization_rule_sets": "OptimizationRuleSet",
    "order_channels": "OrderChannel",
    "order_items": "OrderItem",
    "orders": "Order",
    "page_templates": "PageTemplate",
    "page_versions": "PageVersion",
    "performance_findings": "PerformanceFinding",
    "post_creatives": "PostCreative",
    "posts": "Post",
    "product_concepts": "ProductConcept",
    "product_ideas": "ProductIdea",
    "products": "Product",
    "publication_attempts": "PublicationAttempt",
    "quantity_scenarios": "QuantityScenario",
    "score_factors": "ScoreFactor",
    "scoring_models": "ScoringModel",
    "stored_files": "StoredFile",
    "store_connections": "StoreConnection",
    "stores": "Store",
    "sufficiency_checks": "SufficiencyCheck",
    "test_extensions": "TestExtension",
    "test_result_snapshots": "TestResultSnapshot",
    "tests": "Test",
    "tracking_links": "TrackingLink",
    "tracking_sessions": "TrackingSession",
    "unit_economics": "UnitEconomics",
    "users": "User",
    "verdicts": "Verdict",
}

# Present in a migrated database but owned by the migration tool, not the spec.
TOOL_TABLES: set[str] = {"schema_migrations", "alembic_version"}

DELETE_ACTIONS: dict[str, str] = {
    "a": "NO ACTION",
    "r": "RESTRICT",
    "c": "CASCADE",
    "n": "SET NULL",
    "d": "SET DEFAULT",
}


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    nullable: bool
    default: str | None


@dataclass(frozen=True)
class Constraint:
    name: str
    kind: str
    columns: tuple[str, ...]
    definition: str
    ref_table: str | None = None
    ref_columns: tuple[str, ...] = ()
    on_delete: str | None = None


@dataclass(frozen=True)
class Index:
    name: str
    unique: bool
    definition: str


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[Column, ...] = field(default_factory=tuple)
    constraints: tuple[Constraint, ...] = field(default_factory=tuple)
    indexes: tuple[Index, ...] = field(default_factory=tuple)


def libpq_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def with_database(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{database}"))


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def format_type(
    data_type: str,
    udt_name: str,
    char_length: int | None,
    numeric_precision: int | None,
    numeric_scale: int | None,
) -> str:
    if data_type == "ARRAY":
        return f"{udt_name.lstrip('_')}[]"
    if data_type == "USER-DEFINED":
        return udt_name
    if data_type == "character varying":
        return f"varchar({char_length})" if char_length else "varchar"
    if data_type == "character":
        return f"char({char_length})" if char_length else "char"
    if data_type == "timestamp with time zone":
        return "timestamptz"
    if data_type == "timestamp without time zone":
        return "timestamp"
    if data_type == "numeric" and numeric_precision is not None:
        return f"numeric({numeric_precision},{numeric_scale or 0})"
    return data_type


def fetch_tables(conn: psycopg.Connection) -> list[str]:
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


def fetch_columns(conn: psycopg.Connection, table: str) -> tuple[Column, ...]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, udt_name, is_nullable, column_default,
                   character_maximum_length, numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        return tuple(
            Column(
                name=name,
                type=format_type(data_type, udt_name, char_len, num_prec, num_scale),
                nullable=(is_nullable == "YES"),
                default=default,
            )
            for name, data_type, udt_name, is_nullable, default, char_len, num_prec, num_scale in cur.fetchall()
        )


def fetch_constraints(conn: psycopg.Connection, table: str) -> tuple[Constraint, ...]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT con.conname,
                   con.contype,
                   pg_get_constraintdef(con.oid, true) AS definition,
                   CASE WHEN con.confrelid <> 0
                        THEN con.confrelid::regclass::text END AS ref_table,
                   con.confdeltype,
                   ARRAY(
                       SELECT a.attname
                       FROM unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
                       JOIN pg_attribute a
                         ON a.attrelid = con.conrelid AND a.attnum = k.attnum
                       ORDER BY k.ord
                   ) AS columns,
                   ARRAY(
                       SELECT a.attname
                       FROM unnest(con.confkey) WITH ORDINALITY AS k(attnum, ord)
                       JOIN pg_attribute a
                         ON a.attrelid = con.confrelid AND a.attnum = k.attnum
                       ORDER BY k.ord
                   ) AS ref_columns
            FROM pg_constraint con
            JOIN pg_class t ON t.oid = con.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public' AND t.relname = %s
            ORDER BY con.conname
            """,
            (table,),
        )
        constraints = []
        for name, kind, definition, ref_table, deltype, columns, ref_columns in cur.fetchall():
            constraints.append(
                Constraint(
                    name=name,
                    kind=kind,
                    columns=tuple(columns or ()),
                    definition=definition,
                    ref_table=ref_table,
                    ref_columns=tuple(ref_columns or ()),
                    on_delete=DELETE_ACTIONS.get(deltype) if kind == "f" else None,
                )
            )
        return tuple(constraints)


def fetch_indexes(conn: psycopg.Connection, table: str) -> tuple[Index, ...]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.relname, ix.indisunique, pg_get_indexdef(ix.indexrelid)
            FROM pg_index ix
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_class t ON t.oid = ix.indrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public' AND t.relname = %s
            ORDER BY i.relname
            """,
            (table,),
        )
        return tuple(
            Index(name=name, unique=unique, definition=definition)
            for name, unique, definition in cur.fetchall()
        )


def introspect(conn: psycopg.Connection) -> tuple[Table, ...]:
    tables = []
    for name in fetch_tables(conn):
        tables.append(
            Table(
                name=name,
                columns=fetch_columns(conn, name),
                constraints=fetch_constraints(conn, name),
                indexes=fetch_indexes(conn, name),
            )
        )
    return tuple(tables)


def render_traceability(tables: tuple[Table, ...]) -> list[str]:
    lines = [
        "## Traceability",
        "",
        "Each physical table maps to an entity in `docs/Specifications.md` "
        "(`## Entity Fields`, `## ERD Diagram`). The mapping is explicit in "
        "`scripts/gen_schema_docs.py`; tables marked **UNMAPPED** are drift and "
        "must be added to the spec or the mapping.",
        "",
        "| Table | Specification entity | Status |",
        "| --- | --- | --- |",
    ]
    unmapped = []
    for table in tables:
        entity = ENTITY_BY_TABLE.get(table.name)
        if entity:
            lines.append(f"| `{table.name}` | `{entity}` | mapped |")
        elif table.name in TOOL_TABLES:
            lines.append(f"| `{table.name}` | - | tool-managed |")
        else:
            unmapped.append(table.name)
            lines.append(f"| `{table.name}` | - | **UNMAPPED** |")
    if unmapped:
        lines.extend(
            [
                "",
                "**Warning:** unmapped tables present: "
                + ", ".join(f"`{name}`" for name in unmapped)
                + ". Add them to `ENTITY_BY_TABLE` and `docs/Specifications.md`.",
            ]
        )
    return lines


def render_table(table: Table) -> list[str]:
    entity = ENTITY_BY_TABLE.get(table.name)
    lines = [f"## `{table.name}`", ""]
    if entity:
        lines.append(f"**Specification entity:** `{entity}`")
    elif table.name in TOOL_TABLES:
        lines.append("**Specification entity:** - (tool-managed)")
    else:
        lines.append("**Specification entity:** **UNMAPPED**")
    lines.extend(["", "### Columns", ""])
    lines.append("| # | Column | Type | Nullability | Default |")
    lines.append("| --- | --- | --- | --- | --- |")
    for position, column in enumerate(table.columns, start=1):
        default = f"`{column.default}`" if column.default is not None else "-"
        nullability = "NULL" if column.nullable else "NOT NULL"
        lines.append(
            f"| {position} | `{column.name}` | `{column.type}` | {nullability} | {default} |"
        )

    primary_keys = [c for c in table.constraints if c.kind == "p"]
    lines.extend(["", "### Primary key", ""])
    if primary_keys:
        for constraint in primary_keys:
            columns = ", ".join(f"`{name}`" for name in constraint.columns)
            lines.append(f"- `{constraint.name}` ({columns})")
    else:
        lines.append("- _None._")

    foreign_keys = [c for c in table.constraints if c.kind == "f"]
    lines.extend(["", "### Foreign keys", ""])
    if foreign_keys:
        lines.append("| Name | Columns | References | On delete |")
        lines.append("| --- | --- | --- | --- |")
        for constraint in foreign_keys:
            columns = ", ".join(f"`{name}`" for name in constraint.columns)
            target = ", ".join(f"`{name}`" for name in constraint.ref_columns)
            references = f"`{constraint.ref_table}` ({target})"
            lines.append(
                f"| `{constraint.name}` | {columns} | {references} | "
                f"{constraint.on_delete or 'NO ACTION'} |"
            )
    else:
        lines.append("- _None._")

    uniques = [c for c in table.constraints if c.kind == "u"]
    lines.extend(["", "### Unique constraints", ""])
    if uniques:
        lines.append("| Name | Columns | Notes |")
        lines.append("| --- | --- | --- |")
        for constraint in uniques:
            columns = ", ".join(f"`{name}`" for name in constraint.columns)
            note = (
                "NULLS NOT DISTINCT"
                if "NULLS NOT DISTINCT" in constraint.definition.upper()
                else "-"
            )
            lines.append(f"| `{constraint.name}` | {columns} | {note} |")
    else:
        lines.append("- _None._")

    checks = [c for c in table.constraints if c.kind == "c"]
    lines.extend(["", "### Check constraints", ""])
    if checks:
        for constraint in checks:
            lines.append(f"- `{constraint.name}`: `{constraint.definition}`")
    else:
        lines.append("- _None._")

    lines.extend(["", "### Indexes", ""])
    if table.indexes:
        lines.append("| Name | Unique | Definition |")
        lines.append("| --- | --- | --- |")
        for index in table.indexes:
            unique = "yes" if index.unique else "no"
            lines.append(f"| `{index.name}` | {unique} | `{index.definition}` |")
    else:
        lines.append("- _None._")
    return lines


def render_document(tables: tuple[Table, ...]) -> str:
    column_count = sum(len(table.columns) for table in tables)
    constraint_count = sum(len(table.constraints) for table in tables)
    index_count = sum(len(table.indexes) for table in tables)
    lines = [
        "# Database Schema",
        "",
        "Generated by `scripts/gen_schema_docs.py` from a database migrated to "
        "`alembic upgrade head`. Do not edit this file by hand; regenerate it.",
        "",
        "## Summary",
        "",
        f"- Tables: {len(tables)}",
        f"- Columns: {column_count}",
        f"- Constraints: {constraint_count}",
        f"- Indexes: {index_count}",
        "",
    ]
    lines.extend(render_traceability(tables))
    lines.append("")
    for table in tables:
        lines.extend(render_table(table))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_document(document: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="\n")


def generate(url: str) -> str:
    with psycopg.connect(libpq_url(url)) as conn:
        tables = introspect(conn)
    return render_document(tables)


def display_path(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def run_scratch(output: Path) -> int:
    admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
    if not admin_url:
        print("FAIL: MUSAWIQ_ADMIN_DATABASE_URL is not set", file=sys.stderr)
        return 1

    scratch = f"musawiq_schema_docs_{uuid.uuid4().hex[:10]}"
    scratch_url = with_database(admin_url, scratch)
    admin: psycopg.Connection | None = None
    try:
        admin = psycopg.connect(libpq_url(admin_url), autocommit=True)
        with admin.cursor() as cur:
            cur.execute(f"CREATE DATABASE {quote_ident(scratch)}")
        print(f"created scratch database: {scratch}")

        env = os.environ.copy()
        env["MUSAWIQ_DATABASE_URL"] = scratch_url
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            env=env,
            check=True,
        )

        write_document(generate(scratch_url), output)
        print(f"wrote {display_path(output)}")
        return 0
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        if admin is not None:
            try:
                with admin.cursor() as cur:
                    cur.execute(
                        f"DROP DATABASE IF EXISTS {quote_ident(scratch)} WITH (FORCE)"
                    )
                print(f"dropped scratch database: {scratch}")
            finally:
                admin.close()


def run_url(url: str, output: Path) -> int:
    try:
        write_document(generate(url), output)
        print(f"wrote {display_path(output)}")
        return 0
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


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
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="output path (default: docs/SCHEMA.md)",
    )
    args = parser.parse_args(argv)

    output = args.output if args.output.is_absolute() else ROOT / args.output
    if args.url:
        return run_url(args.url, output)
    return run_scratch(output)


if __name__ == "__main__":
    raise SystemExit(main())
