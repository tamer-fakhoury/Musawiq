"""Static checks for ``scripts/roles.sql``.

The SQL is never executed by this test. These checks guard the contract that the
owner reviews: role names, absence of elevated attributes and credentials,
guarded role creation, and the reporting allow-list.
"""

from __future__ import annotations

import re
from pathlib import Path

ROLES_SQL = Path(__file__).resolve().parents[2] / "scripts" / "roles.sql"

ROLE_NAMES = (
    "musawiq_owner",
    "musawiq_app",
    "musawiq_reporting",
    "musawiq_maintenance",
)

REPORTING_ALLOWED = (
    "countries",
    "currencies",
    "languages",
    "ad_platforms",
    "event_types",
    "categories",
    "niches",
    "products",
    "scoring_models",
    "optimization_rule_sets",
    "decision_rule_sets",
)

REPORTING_FORBIDDEN = (
    "users",
    "orders",
    "order_items",
    "audit_logs",
    "stored_files",
    "feedback_items",
)


def sql_text() -> str:
    return ROLES_SQL.read_text(encoding="utf-8")


def sql_without_line_comments() -> str:
    return re.sub(r"--[^\n]*", "", sql_text())


def reporting_grant_targets(sql: str) -> str:
    targets: list[str] = []
    for grant in re.findall(r"\bGRANT\b(.*?);", sql, re.I | re.S):
        parts = re.split(r"\bTO\b", grant, maxsplit=1, flags=re.I)
        if len(parts) != 2:
            continue
        target, grantees = parts
        if re.search(r"\bmusawiq_reporting\b", grantees, re.I):
            targets.append(target)
    return " ".join(targets)


def test_four_roles_are_present() -> None:
    sql = sql_text()
    for role in ROLE_NAMES:
        assert role in sql


def test_no_elevated_attributes_or_plaintext_credentials() -> None:
    sql = sql_without_line_comments().upper()
    assert not re.search(r"\bSUPERUSER\b", sql)
    assert not re.search(r"\bBYPASSRLS\b", sql)
    assert not re.search(r"\bPASSWORD\b", sql)


def test_every_create_role_is_guarded() -> None:
    sql = sql_without_line_comments()
    creates = re.findall(r"CREATE\s+ROLE\s+(\w+)", sql, re.I)
    assert sorted(creates) == sorted(ROLE_NAMES)

    for name in creates:
        guard = (
            r"IF\s+NOT\s+EXISTS\s*\(\s*SELECT\s+1\s+FROM\s+pg_roles\s+"
            r"WHERE\s+rolname\s*=\s*'"
            + re.escape(name)
            + r"'\s*\)\s*THEN\s*CREATE\s+ROLE\s+"
            + re.escape(name)
            + r"\b"
        )
        assert re.search(guard, sql, re.I | re.S), f"unguarded CREATE ROLE {name}"


def test_reporting_is_limited_to_the_allow_list() -> None:
    targets = reporting_grant_targets(sql_without_line_comments())

    for table in REPORTING_ALLOWED:
        assert re.search(rf"\b{table}\b", targets, re.I), (
            f"missing reporting grant for {table}"
        )
    for table in REPORTING_FORBIDDEN:
        assert not re.search(rf"\b{table}\b", targets, re.I), (
            f"musawiq_reporting must not be granted on {table}"
        )


def test_public_schema_create_is_owner_only() -> None:
    sql = sql_without_line_comments()
    assert re.search(
        r"REVOKE\s+CREATE\s+ON\s+SCHEMA\s+public\s+FROM\s+PUBLIC",
        sql,
        re.I,
    )
    assert not re.search(
        r"GRANT\s+[^;]*\bCREATE\b[^;]*\bTO\b[^;]*\bmusawiq_app\b",
        sql,
        re.I | re.S,
    )
