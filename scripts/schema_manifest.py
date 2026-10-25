"""Schema manifest — the reviewer-visible contract for DB schema parity.

Each DB task adds the tables it creates. ``scripts/parity_check.py`` compares
the live database against this manifest, so a migration that creates a column
nobody declared fails verification.

Column tuples are ``(name, type_group)`` where ``type_group`` is a coarse
bucket (uuid, text, bigint, integer, boolean, timestamptz, date, jsonb, bytea,
numeric, inet, array). Coarse matching keeps the manifest stable across
harmless type-syntax differences while still catching structural mistakes.
"""

from __future__ import annotations

# Tables owned by the current revision chain.
# Populated incrementally by DB-0.3 onward. DB-0.1/0.2 ship zero tables.
TABLES: dict[str, list[tuple[str, str]]] = {}

# Extensions that must be installed.
EXTENSIONS: set[str] = set()

# Functions that must exist in the public schema: name -> language.
FUNCTIONS: dict[str, str] = {}

# Tables that must exist but are managed by the tool, not by our migrations.
TOOL_TABLES = {"schema_migrations", "alembic_version"}

# Tables that are intentionally append-only (no updated_at, mutation blocked).
APPEND_ONLY_TABLES: set[str] = set()

# Tables expected to carry store_id and therefore RLS once DB-0.15 lands.
TENANT_TABLES: set[str] = set()

# Reference/global tables where store_id is nullable by design.
GLOBAL_NULLABLE_TENANT_TABLES: set[str] = {
    "content_provider",
    "niche",
    "scoring_model",
    "optimization_rule_set",
    "decision_rule_set",
    "async_job",
    "audit_log",
}
