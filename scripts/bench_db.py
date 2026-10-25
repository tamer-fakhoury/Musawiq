"""Seed a synthetic dataset and benchmark representative Musawiq queries.

Modes:
    --scratch   create a throwaway database from ``MUSAWIQ_ADMIN_DATABASE_URL``,
                run ``alembic upgrade head``, seed, benchmark, then drop it
    --url DSN   seed and benchmark an existing migrated database

Seeding is idempotent for a dedicated benchmark store. Rows use the schema's
``uuidv7()`` defaults and the reference rows installed by the migrations.
Benchmarks run ``EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`` and report measured
median and p95 execution times. Queries whose tables do not exist are reported
as SKIPPED. Exit code is 1 if a benchmark errors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from scripts.audit_schema import (
    ROOT,
    libpq_url,
    scratch_database,
    table_exists,
)

load_dotenv(ROOT / ".env")

REPORT_PATH = ROOT / "docs" / "PERFORMANCE.md"
BUDGET_MS = 2000.0
WARMUP_RUNS = 1
MEASURED_RUNS = 20

BENCH_EMAIL = "bench@musawiq.invalid"
BENCH_SLUG = "musawiq-bench-store"
BENCH_STORAGE_KEY = "bench/seed.csv"

SCALES: dict[str, dict[str, int]] = {
    "small": {
        "products": 5_000,
        "orders": 20_000,
        "events": 100_000,
        "import_batches": 200,
    },
    "medium": {
        "products": 50_000,
        "orders": 100_000,
        "events": 1_000_000,
        "import_batches": 2_000,
    },
}


@dataclass
class SeedResult:
    store_id: str | None
    products: int = 0
    orders: int = 0
    events: int = 0
    import_batches: int = 0
    notes: list[str] | None = None


@dataclass
class QueryResult:
    name: str
    description: str
    sql: str
    status: str
    reason: str
    median_ms: float | None = None
    p95_ms: float | None = None
    min_ms: float | None = None
    max_ms: float | None = None
    plan_summary: str = ""
    planning_ms: float | None = None
    shared_hit: int | None = None
    shared_read: int | None = None
    budget_verdict: str = "SKIPPED"

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "sql": self.sql,
            "status": self.status,
            "reason": self.reason,
            "median_ms": self.median_ms,
            "p95_ms": self.p95_ms,
            "min_ms": self.min_ms,
            "max_ms": self.max_ms,
            "plan_summary": self.plan_summary,
            "planning_ms": self.planning_ms,
            "shared_hit_blocks": self.shared_hit,
            "shared_read_blocks": self.shared_read,
            "budget_ms": BUDGET_MS,
            "budget_verdict": self.budget_verdict,
        }


def table_columns(conn: psycopg.Connection, table: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table,),
        )
        return {row[0] for row in cur.fetchall()}


def count_rows(conn: psycopg.Connection, table: str, store_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*) FROM {table} WHERE store_id = %s",
            (store_id,),
        )
        return int(cur.fetchone()[0])


def require_reference_rows(conn: psycopg.Connection) -> None:
    checks = (
        ("currencies", "code", "USD"),
        ("languages", "code", "en"),
        ("countries", "code", "US"),
    )
    with conn.cursor() as cur:
        for table, column, value in checks:
            cur.execute(
                f"SELECT EXISTS (SELECT 1 FROM {table} WHERE {column} = %s)",
                (value,),
            )
            if not cur.fetchone()[0]:
                raise RuntimeError(
                    f"reference row missing: {table}.{column} = {value!r}"
                )


def ensure_store(conn: psycopg.Connection) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (email, full_name, role, status)
            VALUES (%s, %s, 'owner', 'active')
            ON CONFLICT (email) DO NOTHING
            """,
            (BENCH_EMAIL, "Benchmark Owner"),
        )
        cur.execute("SELECT id FROM users WHERE email = %s", (BENCH_EMAIL,))
        owner_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO stores (
                owner_user_id, name, slug, status, default_currency,
                default_language, timezone, country_code, onboarding_status,
                settings
            )
            VALUES (
                %s, 'Benchmark Store', %s, 'active', 'USD',
                'en', 'UTC', 'US', 'completed',
                '{"schema_version": 1, "seed": "bench"}'::jsonb
            )
            ON CONFLICT (slug) DO NOTHING
            """,
            (owner_id, BENCH_SLUG),
        )
        cur.execute("SELECT id FROM stores WHERE slug = %s", (BENCH_SLUG,))
        return str(cur.fetchone()[0])


def seed_products(
    conn: psycopg.Connection, store_id: str, target: int
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM products WHERE store_id = %s", (store_id,)
        )
        current = int(cur.fetchone()[0])
        if current < target:
            cur.execute(
                """
                INSERT INTO products (
                    store_id, external_product_id, sku, name, description,
                    currency, cost_minor, price_minor, status, source,
                    metadata, created_at
                )
                SELECT
                    %s,
                    'bench-product-' || g,
                    'BENCH-' || g,
                    'Bench Product ' || g,
                    'Synthetic row for the performance baseline',
                    'USD',
                    1000 + g,
                    2500 + g,
                    CASE WHEN mod(g, 10) = 0 THEN 'archived' ELSE 'active' END,
                    'imported',
                    jsonb_build_object('schema_version', 1, 'seed', 'bench'),
                    now() - (g || ' minutes')::interval
                FROM generate_series(%s::integer, %s::integer) AS g
                ON CONFLICT DO NOTHING
                """,
                (store_id, current, target - 1),
            )
        cur.execute(
            "SELECT count(*) FROM products WHERE store_id = %s", (store_id,)
        )
        return int(cur.fetchone()[0])


def seed_orders(conn: psycopg.Connection, store_id: str, target: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM orders WHERE store_id = %s", (store_id,)
        )
        current = int(cur.fetchone()[0])
        if current < target:
            cur.execute(
                """
                INSERT INTO orders (
                    store_id, origin, external_order_id, order_number, status,
                    currency, subtotal_minor, total_minor, dedupe_hash,
                    placed_at, imported_at, created_at
                )
                SELECT
                    %s,
                    'imported',
                    'bench-order-' || g,
                    'BENCH-' || g,
                    (ARRAY['pending', 'confirmed', 'fulfilled', 'cancelled', 'returned'])
                        [1 + mod(g, 5)],
                    'USD',
                    1000 + g,
                    1000 + g,
                    encode(sha256(convert_to('bench-order-' || g, 'UTF8')), 'hex'),
                    now() - (g || ' minutes')::interval,
                    now() - (g || ' minutes')::interval,
                    now() - (g || ' minutes')::interval
                FROM generate_series(%s::integer, %s::integer) AS g
                ON CONFLICT DO NOTHING
                """,
                (store_id, current, target - 1),
            )
        cur.execute(
            "SELECT count(*) FROM orders WHERE store_id = %s", (store_id,)
        )
        return int(cur.fetchone()[0])


def seed_events(
    conn: psycopg.Connection, store_id: str, target: int, notes: list[str]
) -> int:
    columns = table_columns(conn, "events")
    required = {
        "store_id",
        "event_id",
        "event_type",
        "source",
        "occurred_at",
        "received_at",
        "is_bot",
        "properties",
    }
    if not required <= columns:
        notes.append(
            "event seeding SKIPPED: events table lacks expected columns: "
            + ", ".join(sorted(required - columns))
        )
        return 0

    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM events WHERE store_id = %s", (store_id,)
        )
        current = int(cur.fetchone()[0])
    if current >= target:
        return current

    url_clause = "('https://bench.invalid/p/' || g)" if "url" in columns else "NULL"
    try:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO events (
                        store_id, event_id, event_type, source, url,
                        occurred_at, received_at, is_bot, properties
                    )
                    SELECT
                        %s,
                        uuidv7(),
                        COALESCE(
                            (SELECT code FROM event_types ORDER BY code LIMIT 1),
                            'page_view'
                        ),
                        'web',
                        {url_clause},
                        now() - (g || ' seconds')::interval,
                        now(),
                        false,
                        jsonb_build_object('schema_version', 1, 'seed', 'bench')
                    FROM generate_series(%s::integer, %s::integer) AS g
                    ON CONFLICT DO NOTHING
                    """,
                    (store_id, current, target - 1),
                )
    except Exception as exc:
        notes.append(f"event seeding SKIPPED: {type(exc).__name__}: {exc}")
        return current

    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM events WHERE store_id = %s", (store_id,)
        )
        return int(cur.fetchone()[0])


def ensure_stored_file(conn: psycopg.Connection, store_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM stored_files
            WHERE store_id = %s AND storage_key = %s
            LIMIT 1
            """,
            (store_id, BENCH_STORAGE_KEY),
        )
        row = cur.fetchone()
        if row:
            return str(row[0])
        cur.execute(
            """
            INSERT INTO stored_files (
                store_id, purpose, original_filename, mime_type, size_bytes,
                checksum_sha256, storage_provider, storage_key, status
            )
            VALUES (
                %s, 'sales_csv', 'bench.csv', 'text/csv', 0,
                repeat('0', 64), 'bench', %s, 'committed'
            )
            RETURNING id
            """,
            (store_id, BENCH_STORAGE_KEY),
        )
        return str(cur.fetchone()[0])


def seed_import_batches(
    conn: psycopg.Connection, store_id: str, target: int
) -> int:
    file_id = ensure_stored_file(conn, store_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM users WHERE email = %s
            """,
            (BENCH_EMAIL,),
        )
        user_id = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM import_batches WHERE store_id = %s",
            (store_id,),
        )
        current = int(cur.fetchone()[0])
        if current < target:
            cur.execute(
                """
                INSERT INTO import_batches (
                    store_id, source_type, stored_file_id, status, strict_mode,
                    total_rows, valid_rows, imported_rows, started_at,
                    completed_at, created_by, created_at
                )
                SELECT
                    %s,
                    'csv',
                    %s,
                    'completed',
                    true,
                    100,
                    100,
                    100,
                    now() - (g || ' hours')::interval,
                    now() - (g || ' hours')::interval + interval '5 minutes',
                    %s,
                    now() - (g || ' hours')::interval
                FROM generate_series(%s::integer, %s::integer) AS g
                """,
                (store_id, file_id, user_id, current, target - 1),
            )
        cur.execute(
            "SELECT count(*) FROM import_batches WHERE store_id = %s",
            (store_id,),
        )
        return int(cur.fetchone()[0])


def seed_dataset(conn: psycopg.Connection, scale: str) -> SeedResult:
    targets = SCALES[scale]
    notes: list[str] = []
    missing = [table for table in ("users", "stores") if not table_exists(conn, table)]
    if missing:
        return SeedResult(
            store_id=None,
            notes=["seeding SKIPPED: table missing: " + ", ".join(missing)],
        )

    require_reference_rows(conn)
    store_id = ensure_store(conn)
    products = 0
    orders = 0
    events = 0
    import_batches = 0

    if table_exists(conn, "products"):
        products = seed_products(conn, store_id, targets["products"])
    else:
        notes.append("product seeding SKIPPED: table missing: products")

    if table_exists(conn, "orders"):
        orders = seed_orders(conn, store_id, targets["orders"])
    else:
        notes.append("order seeding SKIPPED: table missing: orders")

    if table_exists(conn, "events"):
        events = seed_events(conn, store_id, targets["events"], notes)
    else:
        notes.append("event seeding SKIPPED: table missing: events")

    if table_exists(conn, "import_batches") and table_exists(
        conn, "stored_files"
    ):
        import_batches = seed_import_batches(
            conn, store_id, targets["import_batches"]
        )
    else:
        notes.append(
            "import seeding SKIPPED: table missing: "
            + ", ".join(
                table
                for table in ("import_batches", "stored_files")
                if not table_exists(conn, table)
            )
        )

    for table in ("products", "orders", "events", "import_batches"):
        if table_exists(conn, table):
            with conn.cursor() as cur:
                cur.execute(f"ANALYZE {table}")
    conn.commit()

    return SeedResult(
        store_id=store_id,
        products=products,
        orders=orders,
        events=events,
        import_batches=import_batches,
        notes=notes,
    )


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    rank = max(0, math.ceil(p / 100.0 * len(ordered)) - 1)
    return ordered[min(rank, len(ordered) - 1)]


def plan_nodes(plan: dict[str, object]) -> list[dict[str, object]]:
    nodes = [plan]
    for child in plan.get("Plans", []):
        nodes.extend(plan_nodes(child))
    return nodes


def summarize_plan(document: dict[str, object]) -> str:
    plan = document["Plan"]
    labels = []
    for node in plan_nodes(plan):
        label = str(node.get("Node Type", "?"))
        relation = node.get("Relation Name")
        index = node.get("Index Name")
        if relation:
            label += f" on {relation}"
        if index:
            label += f" using {index}"
        rows = node.get("Actual Rows")
        if rows is not None:
            label += f" (rows={rows})"
        labels.append(label)
    return " > ".join(labels)


def explain_once(
    conn: psycopg.Connection, sql: str, params: tuple[object, ...]
) -> dict[str, object]:
    with conn.cursor() as cur:
        cur.execute(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql,
            params,
        )
        value = cur.fetchone()[0]
    document = json.loads(value) if isinstance(value, str) else value
    return document[0]


def benchmark_query(
    conn: psycopg.Connection,
    name: str,
    description: str,
    sql: str,
    params: tuple[object, ...],
    runs: int,
) -> QueryResult:
    document: dict[str, object] | None = None
    try:
        for _ in range(WARMUP_RUNS):
            document = explain_once(conn, sql, params)
        timings: list[float] = []
        for _ in range(runs):
            document = explain_once(conn, sql, params)
            timings.append(float(document["Execution Time"]))
    except Exception as exc:
        return QueryResult(
            name=name,
            description=description,
            sql=sql.strip(),
            status="ERROR",
            reason=f"{type(exc).__name__}: {exc}",
        )

    assert document is not None
    plan = document["Plan"]
    median_ms = statistics.median(timings)
    p95_ms = percentile(timings, 95)
    return QueryResult(
        name=name,
        description=description,
        sql=sql.strip(),
        status="PASS",
        reason=f"{len(timings)} measured runs",
        median_ms=round(median_ms, 3),
        p95_ms=round(p95_ms, 3),
        min_ms=round(min(timings), 3),
        max_ms=round(max(timings), 3),
        plan_summary=summarize_plan(document),
        planning_ms=round(float(document.get("Planning Time", 0.0)), 3),
        shared_hit=int(plan.get("Shared Hit Blocks", 0) or 0),
        shared_read=int(plan.get("Shared Read Blocks", 0) or 0),
        budget_verdict="PASS" if p95_ms < BUDGET_MS else "FAIL",
    )


def query_specs(
    store_id: str,
) -> list[tuple[str, str, str, tuple[str, str], tuple[str, ...]]]:
    dedupe = hashlib.sha256(b"bench-order-1").hexdigest()
    return [
        (
            "products_by_store_status",
            "Products filtered by store and status",
            """
            SELECT id, name, price_minor, created_at
            FROM products
            WHERE store_id = %s AND status = 'active'
            ORDER BY created_at DESC
            LIMIT 100
            """,
            (store_id,),
            ("products",),
        ),
        (
            "orders_by_store_placed_at",
            "Orders filtered by store and date window",
            """
            SELECT id, total_minor, placed_at
            FROM orders
            WHERE store_id = %s
              AND placed_at >= now() - interval '30 days'
            ORDER BY placed_at DESC
            LIMIT 100
            """,
            (store_id,),
            ("orders",),
        ),
        (
            "order_by_store_dedupe_hash",
            "Order lookup by store and dedupe hash",
            """
            SELECT id, order_number, total_minor
            FROM orders
            WHERE store_id = %s AND dedupe_hash = %s
            """,
            (store_id, dedupe),
            ("orders",),
        ),
        (
            "import_history_by_store",
            "Import history for a store, newest first",
            """
            SELECT id, status, total_rows, created_at
            FROM import_batches
            WHERE store_id = %s
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (store_id,),
            ("import_batches",),
        ),
    ]


def run_benchmarks(
    conn: psycopg.Connection,
    seed: SeedResult,
    runs: int,
) -> list[QueryResult]:
    if seed.store_id is None:
        reason = "seeding skipped; no benchmark store available"
        return [
            QueryResult(
                name=name,
                description=description,
                sql=sql.strip(),
                status="SKIPPED",
                reason=reason,
            )
            for name, description, sql, _, _ in query_specs(
                "00000000-0000-0000-0000-000000000000"
            )
        ]

    results = []
    for name, description, sql, params, tables in query_specs(seed.store_id):
        missing = [table for table in tables if not table_exists(conn, table)]
        if missing:
            results.append(
                QueryResult(
                    name=name,
                    description=description,
                    sql=sql.strip(),
                    status="SKIPPED",
                    reason="table missing: " + ", ".join(missing),
                )
            )
            continue
        results.append(
            benchmark_query(
                conn, name, description, sql, params, runs
            )
        )
    return results


def render_text(
    version: str, scale: str, seed: SeedResult, results: list[QueryResult]
) -> str:
    lines = [
        "Performance Baseline",
        "====================",
        f"PostgreSQL: {version}",
        f"Scale: {scale}",
        f"Seeded: products={seed.products}, orders={seed.orders}, "
        f"events={seed.events}, import_batches={seed.import_batches}",
        f"Runs per query: {MEASURED_RUNS} (+{WARMUP_RUNS} warmup)",
        f"Budget: p95 < {BUDGET_MS:.0f} ms",
        "",
    ]
    for note in seed.notes or []:
        lines.append(f"NOTE: {note}")
    if seed.notes:
        lines.append("")
    for result in results:
        lines.append(f"[{result.status}] {result.name}")
        if result.status == "SKIPPED":
            lines.append(f"    {result.reason}")
            continue
        if result.status == "ERROR":
            lines.append(f"    ERROR: {result.reason}")
            continue
        lines.append(
            f"    median={result.median_ms:.3f} ms p95={result.p95_ms:.3f} ms "
            f"min={result.min_ms:.3f} ms max={result.max_ms:.3f} ms"
        )
        lines.append(f"    plan: {result.plan_summary}")
        lines.append(
            f"    buffers: shared_hit={result.shared_hit} "
            f"shared_read={result.shared_read}"
        )
        lines.append(f"    budget: {result.budget_verdict}")
    measured = [r for r in results if r.status == "PASS"]
    errors = [r for r in results if r.status == "ERROR"]
    over = [r for r in measured if r.budget_verdict == "FAIL"]
    if errors:
        outcome = "BENCHMARK ERROR"
    elif not measured:
        outcome = "SKIPPED"
    elif over:
        outcome = "OVER BUDGET"
    else:
        outcome = "PASS"
    lines.extend(["", f"Overall: {outcome}"])
    return "\n".join(lines) + "\n"


def render_markdown(
    version: str, scale: str, seed: SeedResult, results: list[QueryResult]
) -> str:
    lines = [
        "# Performance Baseline",
        "",
        "Generated by `scripts/bench_db.py` from measured "
        "`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` runs. Regenerate with:",
        "",
        "```",
        f"python -m scripts.bench_db --scratch --scale {scale} --write-report",
        "```",
        "",
        f"- PostgreSQL: {version}",
        f"- Scale: {scale}",
        f"- Seeded: products={seed.products}, orders={seed.orders}, "
        f"events={seed.events}, import_batches={seed.import_batches}",
        f"- Measured runs per query: {MEASURED_RUNS} (plus {WARMUP_RUNS} warmup)",
        f"- Budget: p95 < {BUDGET_MS:.0f} ms",
        "",
    ]
    for note in seed.notes or []:
        lines.append(f"- Note: {note}")
    if seed.notes:
        lines.append("")

    lines.extend(
        [
            "## Summary",
            "",
            "| Query | Status | Median (ms) | P95 (ms) | Budget |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for result in results:
        median = f"{result.median_ms:.3f}" if result.median_ms is not None else "-"
        p95 = f"{result.p95_ms:.3f}" if result.p95_ms is not None else "-"
        lines.append(
            f"| `{result.name}` | {result.status} | {median} | {p95} | "
            f"{result.budget_verdict} |"
        )
    lines.append("")

    for result in results:
        lines.extend(
            [
                f"## `{result.name}`",
                "",
                result.description,
                "",
                "```sql",
                result.sql,
                "```",
                "",
            ]
        )
        if result.status == "SKIPPED":
            lines.extend([f"**SKIPPED** - {result.reason}", ""])
            continue
        if result.status == "ERROR":
            lines.extend([f"**ERROR** - {result.reason}", ""])
            continue
        lines.extend(
            [
                f"- Plan: `{result.plan_summary}`",
                f"- Planning time: {result.planning_ms:.3f} ms",
                f"- Median: {result.median_ms:.3f} ms",
                f"- P95: {result.p95_ms:.3f} ms",
                f"- Min / max: {result.min_ms:.3f} ms / {result.max_ms:.3f} ms",
                f"- Buffers: shared hit {result.shared_hit}, "
                f"shared read {result.shared_read}",
                f"- Budget verdict: **{result.budget_verdict}** "
                f"(p95 < {BUDGET_MS:.0f} ms)",
                "",
            ]
        )

    measured = [r for r in results if r.status == "PASS"]
    errors = [r for r in results if r.status == "ERROR"]
    over = [r for r in measured if r.budget_verdict == "FAIL"]
    if errors:
        outcome = "BENCHMARK ERROR"
    elif not measured:
        outcome = "SKIPPED"
    elif over:
        outcome = "OVER BUDGET"
    else:
        outcome = "PASS"
    lines.extend(["## Verdict", "", f"**{outcome}**", ""])
    return "\n".join(lines).rstrip() + "\n"


def write_markdown(
    version: str, scale: str, seed: SeedResult, results: list[QueryResult]
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        render_markdown(version, scale, seed, results),
        encoding="utf-8",
        newline="\n",
    )


def run(url: str, scale: str, runs: int) -> tuple[str, SeedResult, list[QueryResult]]:
    conn = psycopg.connect(libpq_url(url))
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW server_version")
            version = cur.fetchone()[0]
        print("seeding synthetic benchmark rows", file=sys.stderr)
        seed = seed_dataset(conn, scale)
        print("running EXPLAIN (ANALYZE, BUFFERS) benchmarks", file=sys.stderr)
        results = run_benchmarks(conn, seed, runs)
        return version, seed, results
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--scratch",
        action="store_true",
        help="create a throwaway database from MUSAWIQ_ADMIN_DATABASE_URL (default)",
    )
    group.add_argument("--url", help="seed and benchmark an existing database")
    parser.add_argument(
        "--scale",
        choices=sorted(SCALES),
        default="small",
        help="dataset scale (default: small)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=MEASURED_RUNS,
        help=f"measured runs per query (default: {MEASURED_RUNS})",
    )
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="write the markdown report to docs/PERFORMANCE.md",
    )
    args = parser.parse_args(argv)

    if args.runs < 1:
        print("FAIL: --runs must be at least 1", file=sys.stderr)
        return 1

    try:
        if args.url:
            version, seed, results = run(args.url, args.scale, args.runs)
        else:
            with scratch_database(prefix="musawiq_bench", quiet=False) as url:
                version, seed, results = run(url, args.scale, args.runs)
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.write_report:
        write_markdown(version, args.scale, seed, results)
        print(
            f"wrote {REPORT_PATH.relative_to(ROOT)}",
            file=sys.stderr,
        )

    print(render_text(version, args.scale, seed, results), end="")
    return 1 if any(result.status == "ERROR" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
