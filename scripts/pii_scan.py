"""Scan the migrated schema for unclassified personal data.

The registry in this module is the machine-checkable projection of
``docs/PII.md``. Modes mirror ``scripts/gen_schema_docs.py``:

    --scratch   create a throwaway database from ``MUSAWIQ_ADMIN_DATABASE_URL``,
                run ``alembic upgrade head``, introspect, then drop it (default)
    --url DSN   introspect an existing migrated database

Checks:
    1. every column matching a PII heuristic has a registry entry;
    2. every ``*_enc``/``*_encrypted`` column is ``bytea``/``text`` and is
       classified ``secret`` or ``sensitive_pii``;
    3. no column named ``ip_address`` exists anywhere.

The scan never prints column values. It prints schema names only. Exit code is
1 when the overall status is FAIL, 0 for PASS or SKIPPED.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass

import psycopg
from dotenv import load_dotenv

from scripts.gen_schema_docs import (
    ROOT,
    Column,
    Table,
    introspect,
    libpq_url,
    quote_ident,
    with_database,
)

load_dotenv(ROOT / ".env")

CLASSES = {"public", "internal", "pii", "sensitive_pii", "secret"}
PROTECTIONS = {"none", "hash", "ciphertext", "access-restricted"}

# Tables where a column named like "name" is treated as user data even without
# one of the stronger heuristic tokens. Store/product/campaign names are
# business data, not user data, and are deliberately excluded.
USERISH_TABLES = {"users", "orders"}

HEURISTIC_TOKENS = (
    "email",
    "phone",
    "full_name",
    "address",
    "ip_address",
    "ip_hash",
    "password",
    "secret",
    "token",
    "auth_subject",
)

# Timestamps such as token_expires_at or email_verified_at describe when
# something happened; they do not carry the identifier itself. The heuristic
# skips the _at suffix so these metadata columns do not need registry rows.
TEMPORAL_SUFFIXES = ("_at",)


@dataclass(frozen=True)
class PiiEntry:
    table: str
    column: str
    classification: str
    protection: str
    notes: str


# One row per column that can hold personal data. Future tables are included so
# the registry does not drift when later migrations land; the scan reports them
# as SKIPPED until the columns exist. Keep this in sync with docs/PII.md.
REGISTRY_ROWS: tuple[PiiEntry, ...] = (
    PiiEntry(
        "ad_account_connections",
        "access_token_encrypted",
        "secret",
        "ciphertext",
        "OAuth access token; ciphertext only.",
    ),
    PiiEntry(
        "ad_account_connections",
        "refresh_token_encrypted",
        "secret",
        "ciphertext",
        "OAuth refresh token; ciphertext only.",
    ),
    PiiEntry(
        "async_jobs",
        "payload",
        "sensitive_pii",
        "access-restricted",
        "Job input can embed user-supplied import/generation data.",
    ),
    PiiEntry(
        "async_jobs",
        "result",
        "sensitive_pii",
        "access-restricted",
        "Job output can embed user-supplied data; never expose to reporting.",
    ),
    PiiEntry(
        "audit_logs",
        "after",
        "sensitive_pii",
        "access-restricted",
        "JSONB snapshot can contain order/user data.",
    ),
    PiiEntry(
        "audit_logs",
        "before",
        "sensitive_pii",
        "access-restricted",
        "JSONB snapshot can contain order/user data.",
    ),
    PiiEntry(
        "audit_logs",
        "ip_hash",
        "pii",
        "hash",
        "Hashed request address; raw address is never stored.",
    ),
    PiiEntry(
        "audit_logs",
        "metadata",
        "sensitive_pii",
        "access-restricted",
        "Free-form audit metadata; may carry identifiers.",
    ),
    PiiEntry(
        "audience_profiles",
        "notes",
        "internal",
        "access-restricted",
        "Free text; may include customer observations.",
    ),
    PiiEntry(
        "content_generation_jobs",
        "negative_prompt",
        "internal",
        "access-restricted",
        "User-supplied generation text.",
    ),
    PiiEntry(
        "content_generation_jobs",
        "prompt",
        "internal",
        "access-restricted",
        "User-supplied generation text.",
    ),
    PiiEntry(
        "content_providers",
        "auth_config_encrypted",
        "secret",
        "ciphertext",
        "Provider credentials; ciphertext only.",
    ),
    PiiEntry(
        "evaluations",
        "input_snapshot",
        "internal",
        "access-restricted",
        "Audience/context snapshot; no direct customer identifiers.",
    ),
    PiiEntry(
        "feedback_items",
        "text",
        "sensitive_pii",
        "access-restricted",
        "Free-text feedback can contain any customer detail.",
    ),
    PiiEntry(
        "generation_runs",
        "input_snapshot",
        "internal",
        "access-restricted",
        "Recommendation input snapshot; treat as tenant-confidential.",
    ),
    PiiEntry(
        "import_issues",
        "message",
        "sensitive_pii",
        "access-restricted",
        "Validation messages may echo raw row values.",
    ),
    PiiEntry(
        "import_issues",
        "raw_value",
        "sensitive_pii",
        "access-restricted",
        "Rejected field value from an imported file.",
    ),
    PiiEntry(
        "import_rows",
        "normalized_data",
        "sensitive_pii",
        "access-restricted",
        "Normalized imported row; may contain customer details.",
    ),
    PiiEntry(
        "import_rows",
        "raw_data",
        "sensitive_pii",
        "access-restricted",
        "Raw imported row; may contain customer details.",
    ),
    PiiEntry(
        "order_channels",
        "whatsapp_number",
        "sensitive_pii",
        "access-restricted",
        "Business contact number; restrict to tenant readers.",
    ),
    PiiEntry(
        "orders",
        "customer_address_enc",
        "sensitive_pii",
        "ciphertext",
        "Encrypted delivery address.",
    ),
    PiiEntry(
        "orders",
        "customer_name",
        "sensitive_pii",
        "access-restricted",
        "Plaintext in DB-0.5; encrypt or keep behind restricted access.",
    ),
    PiiEntry(
        "orders",
        "customer_phone",
        "sensitive_pii",
        "access-restricted",
        "Plaintext in DB-0.5; encrypt or keep behind restricted access.",
    ),
    PiiEntry(
        "product_ideas",
        "rationale",
        "internal",
        "none",
        "Model-generated rationale; may quote user context, no direct identifiers.",
    ),
    PiiEntry(
        "stored_files",
        "checksum_sha256",
        "internal",
        "none",
        "Content checksum; not reversible and not a PII locator.",
    ),
    PiiEntry(
        "stored_files",
        "metadata",
        "internal",
        "access-restricted",
        "Uploader-supplied metadata; review before exposing.",
    ),
    PiiEntry(
        "stored_files",
        "original_filename",
        "sensitive_pii",
        "access-restricted",
        "Filenames can contain customer names or document titles.",
    ),
    PiiEntry(
        "stored_files",
        "storage_key",
        "internal",
        "access-restricted",
        "Object-store locator; never expose to clients.",
    ),
    PiiEntry(
        "store_connections",
        "access_token_encrypted",
        "secret",
        "ciphertext",
        "OAuth access token; ciphertext only.",
    ),
    PiiEntry(
        "store_connections",
        "refresh_token_encrypted",
        "secret",
        "ciphertext",
        "OAuth refresh token; ciphertext only.",
    ),
    PiiEntry(
        "users",
        "auth_subject",
        "sensitive_pii",
        "access-restricted",
        "External identity subject; linkable identifier.",
    ),
    PiiEntry(
        "users",
        "email",
        "pii",
        "access-restricted",
        "Account identifier; citext, unique.",
    ),
    PiiEntry(
        "users",
        "full_name",
        "pii",
        "access-restricted",
        "Direct identifier.",
    ),
    PiiEntry(
        "users",
        "password_hash",
        "secret",
        "hash",
        "One-way credential hash; never log or return.",
    ),
    PiiEntry(
        "users",
        "phone",
        "pii",
        "access-restricted",
        "Direct contact identifier.",
    ),
    PiiEntry(
        "tracking_sessions",
        "ip_hash",
        "pii",
        "hash",
        "Planned table; hashed address only.",
    ),
    PiiEntry(
        "events",
        "ip_hash",
        "pii",
        "hash",
        "Planned table; hashed address only.",
    ),
    PiiEntry(
        "events",
        "properties",
        "sensitive_pii",
        "access-restricted",
        "Planned table; event payload can contain form data.",
    ),
    PiiEntry(
        "events",
        "referrer",
        "internal",
        "access-restricted",
        "Planned table; URLs can carry query parameters.",
    ),
    PiiEntry(
        "events",
        "url",
        "internal",
        "access-restricted",
        "Planned table; URLs can carry query parameters.",
    ),
    PiiEntry(
        "tracking_links",
        "token",
        "internal",
        "none",
        "Planned table; public attribution token, not a user credential.",
    ),
    PiiEntry(
        "tracking_sessions",
        "referrer",
        "internal",
        "access-restricted",
        "Planned table; URLs can carry query parameters.",
    ),
    PiiEntry(
        "tracking_sessions",
        "user_agent",
        "internal",
        "access-restricted",
        "Planned table; browser fingerprint may aid re-identification.",
    ),
)

REGISTRY: dict[tuple[str, str], PiiEntry] = {
    (entry.table, entry.column): entry for entry in REGISTRY_ROWS
}

for _entry in REGISTRY_ROWS:
    if _entry.classification not in CLASSES:
        raise ValueError(f"invalid PII class for {_entry.table}.{_entry.column}")
    if _entry.protection not in PROTECTIONS:
        raise ValueError(f"invalid protection for {_entry.table}.{_entry.column}")


@dataclass(frozen=True)
class Finding:
    check: str
    table: str
    column: str
    message: str


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class ScanResult:
    status: str
    table_count: int
    registry_entries: int
    checks: tuple[CheckResult, ...]
    findings: tuple[Finding, ...]


def iter_heuristic_columns(tables: Sequence[Table]) -> Iterator[tuple[Table, Column]]:
    for table in tables:
        table_name = table.name.lower()
        for column in table.columns:
            name = column.name.lower()
            if name.endswith(TEMPORAL_SUFFIXES):
                continue
            matched = any(token in name for token in HEURISTIC_TOKENS)
            if not matched and table_name in USERISH_TABLES and "name" in name:
                matched = True
            if matched:
                yield table, column


def is_encrypted_column(name: str) -> bool:
    lower = name.lower()
    return lower.endswith("_enc") or lower.endswith("_encrypted")


def scan_tables(tables: Sequence[Table]) -> ScanResult:
    checks: list[CheckResult] = []
    findings: list[Finding] = []

    heuristic_columns = list(iter_heuristic_columns(tables))
    if not tables:
        checks.append(CheckResult("heuristic_coverage", "SKIPPED", "no tables"))
    elif not heuristic_columns:
        checks.append(
            CheckResult("heuristic_coverage", "SKIPPED", "no heuristic columns")
        )
    else:
        for table, column in heuristic_columns:
            entry = REGISTRY.get((table.name, column.name))
            if entry is None:
                findings.append(
                    Finding(
                        "heuristic_coverage",
                        table.name,
                        column.name,
                        "column matches a PII heuristic but is not in the registry",
                    )
                )
        checks.append(
            CheckResult(
                "heuristic_coverage",
                "FAIL"
                if any(f.check == "heuristic_coverage" for f in findings)
                else "PASS",
                f"{len(heuristic_columns)} columns checked",
            )
        )

    encrypted_columns = [
        (table, column)
        for table in tables
        for column in table.columns
        if is_encrypted_column(column.name)
    ]
    if not encrypted_columns:
        checks.append(
            CheckResult("encrypted_columns", "SKIPPED", "no encrypted columns")
        )
    else:
        for table, column in encrypted_columns:
            entry = REGISTRY.get((table.name, column.name))
            if entry is None:
                findings.append(
                    Finding(
                        "encrypted_columns",
                        table.name,
                        column.name,
                        "encrypted column is not in the registry",
                    )
                )
                continue
            if column.type not in {"bytea", "text"}:
                findings.append(
                    Finding(
                        "encrypted_columns",
                        table.name,
                        column.name,
                        f"encrypted column has type {column.type}; expected bytea or text",
                    )
                )
            if entry.classification not in {"secret", "sensitive_pii"}:
                findings.append(
                    Finding(
                        "encrypted_columns",
                        table.name,
                        column.name,
                        f"encrypted column is classified {entry.classification}; "
                        "expected secret or sensitive_pii",
                    )
                )
        checks.append(
            CheckResult(
                "encrypted_columns",
                "FAIL"
                if any(f.check == "encrypted_columns" for f in findings)
                else "PASS",
                f"{len(encrypted_columns)} columns checked",
            )
        )

    raw_ip_columns = [
        (table, column)
        for table in tables
        for column in table.columns
        if column.name.lower() == "ip_address"
    ]
    if not tables:
        checks.append(CheckResult("raw_ip_columns", "SKIPPED", "no tables"))
    else:
        for table, column in raw_ip_columns:
            findings.append(
                Finding(
                    "raw_ip_columns",
                    table.name,
                    column.name,
                    "raw IP column is forbidden; store ip_hash char(64) instead",
                )
            )
        checks.append(
            CheckResult(
                "raw_ip_columns",
                "FAIL"
                if any(f.check == "raw_ip_columns" for f in findings)
                else "PASS",
                f"{len(raw_ip_columns)} raw IP columns",
            )
        )

    present = {
        (table.name, column.name)
        for table in tables
        for column in table.columns
    }
    future_entries = [key for key in REGISTRY if key not in present]
    checks.append(
        CheckResult(
            "planned_registry_coverage",
            "SKIPPED" if future_entries else "PASS",
            f"{len(future_entries)} registry entries not present at this revision",
        )
    )

    if not tables:
        status = "SKIPPED"
    elif any(check.status == "FAIL" for check in checks):
        status = "FAIL"
    else:
        status = "PASS"

    return ScanResult(
        status=status,
        table_count=len(tables),
        registry_entries=len(REGISTRY),
        checks=tuple(checks),
        findings=tuple(findings),
    )


def scan_database(url: str) -> ScanResult:
    with psycopg.connect(libpq_url(url)) as conn:
        tables = introspect(conn)
    return scan_tables(tables)


@contextmanager
def scratch_database(admin_url: str) -> Iterator[str]:
    scratch = f"musawiq_pii_scan_{uuid.uuid4().hex[:10]}"
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


def print_human(result: ScanResult) -> None:
    print(f"PII SCAN {result.status}")
    print(f"  tables: {result.table_count}")
    print(f"  registry entries: {result.registry_entries}")
    for check in result.checks:
        print(f"  {check.name}: {check.status} ({check.detail})")
    for finding in result.findings:
        print(
            f"  FAIL {finding.check}: {finding.table}.{finding.column}: "
            f"{finding.message}"
        )


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
        "--json",
        action="store_true",
        help="emit a machine-readable result on stdout",
    )
    args = parser.parse_args(argv)

    try:
        if args.url:
            result = scan_database(args.url)
        else:
            admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
            if not admin_url:
                print(
                    "FAIL: MUSAWIQ_ADMIN_DATABASE_URL is not set",
                    file=sys.stderr,
                )
                return 1
            with scratch_database(admin_url) as url:
                result = scan_database(url)
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print_human(result)
    return 1 if result.status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
