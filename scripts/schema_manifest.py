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
TABLES: dict[str, list[tuple[str, str]]] = {
    "ad_platforms": [
        ("code", "text"),
        ("name", "text"),
        ("is_active", "boolean"),
    ],
    "countries": [
        ("code", "text"),
        ("name", "text"),
        ("is_active", "boolean"),
    ],
    "currencies": [
        ("code", "text"),
        ("name", "text"),
        ("minor_unit", "integer"),
        ("is_active", "boolean"),
    ],
    "event_types": [
        ("code", "text"),
        ("description", "text"),
        ("is_active", "boolean"),
    ],
    "languages": [
        ("code", "text"),
        ("name", "text"),
        ("direction", "text"),
        ("is_active", "boolean"),
    ],
    "users": [
        ("id", "uuid"),
        ("email", "text"),
        ("password_hash", "text"),
        ("full_name", "text"),
        ("phone", "text"),
        ("locale", "text"),
        ("timezone", "text"),
        ("role", "text"),
        ("status", "text"),
        ("email_verified_at", "timestamptz"),
        ("last_login_at", "timestamptz"),
        ("auth_provider", "text"),
        ("auth_subject", "text"),
        ("deleted_at", "timestamptz"),
        ("created_at", "timestamptz"),
        ("updated_at", "timestamptz"),
    ],
    "stores": [
        ("id", "uuid"),
        ("owner_user_id", "uuid"),
        ("name", "text"),
        ("slug", "text"),
        ("status", "text"),
        ("default_currency", "text"),
        ("default_language", "text"),
        ("timezone", "text"),
        ("country_code", "text"),
        ("onboarding_status", "text"),
        ("settings", "jsonb"),
        ("deleted_at", "timestamptz"),
        ("created_at", "timestamptz"),
        ("updated_at", "timestamptz"),
    ],
    "audit_logs": [
        ("id", "uuid"),
        ("store_id", "uuid"),
        ("actor_user_id", "uuid"),
        ("actor_type", "text"),
        ("action", "text"),
        ("target_type", "text"),
        ("target_id", "uuid"),
        ("before", "jsonb"),
        ("after", "jsonb"),
        ("metadata", "jsonb"),
        ("ip_hash", "text"),
        ("user_agent", "text"),
        ("correlation_id", "uuid"),
        ("created_at", "timestamptz"),
    ],
    "async_jobs": [
        ("id", "uuid"),
        ("store_id", "uuid"),
        ("job_type", "text"),
        ("state", "text"),
        ("idempotency_key", "text"),
        ("payload", "jsonb"),
        ("result", "jsonb"),
        ("progress_current", "integer"),
        ("progress_total", "integer"),
        ("attempt_count", "integer"),
        ("max_attempts", "integer"),
        ("error_code", "text"),
        ("error_message", "text"),
        ("correlation_id", "uuid"),
        ("scheduled_at", "timestamptz"),
        ("started_at", "timestamptz"),
        ("finished_at", "timestamptz"),
        ("created_at", "timestamptz"),
        ("updated_at", "timestamptz"),
    ],
}

# Extensions that must be installed.
EXTENSIONS: set[str] = {"citext", "pg_trgm"}

# Functions that must exist in the public schema: name -> language.
FUNCTIONS: dict[str, str] = {
    "fn_block_mutation": "plpgsql",
    "fn_touch_updated_at": "plpgsql",
}

# Tables that must exist but are managed by the tool, not by our migrations.
TOOL_TABLES = {"schema_migrations", "alembic_version"}

# Tables that are intentionally append-only (no updated_at, mutation blocked).
APPEND_ONLY_TABLES: set[str] = {"audit_logs"}

# Tables expected to carry store_id and therefore RLS once DB-0.15 lands.
TENANT_TABLES: set[str] = set()

# Reference/global tables where store_id is nullable by design.
GLOBAL_NULLABLE_TENANT_TABLES: set[str] = {
    "content_providers",
    "niches",
    "scoring_models",
    "optimization_rule_sets",
    "decision_rule_sets",
    "async_jobs",
    "audit_logs",
}
