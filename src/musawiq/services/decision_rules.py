"""Versioned decision rule configuration (FR-5.1.3)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.services.audit import AuditService

INTEGER_FIELDS = (
    "min_spend_minor",
    "min_clicks",
    "min_conversions",
    "min_confirmed_deposits",
    "max_cost_per_conversion_minor",
)


class DecisionRuleError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _integer(value: object, name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DecisionRuleError(
            f"invalid_{name}", f"{name} must be a non-negative integer."
        )
    return value


def _rate(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DecisionRuleError(
            "invalid_min_conversion_rate",
            "min_conversion_rate must be between 0 and 1.",
        )
    rate = float(value)
    if not 0 <= rate <= 1:
        raise DecisionRuleError(
            "invalid_min_conversion_rate",
            "min_conversion_rate must be between 0 and 1.",
        )
    return rate


def _category(session: Session, category_id: object) -> uuid.UUID | None:
    if category_id is None:
        return None
    try:
        value = uuid.UUID(str(category_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise DecisionRuleError(
            "invalid_category_id", "category_id must be a UUID."
        ) from exc
    exists = session.execute(
        text("SELECT 1 FROM categories WHERE id = :id"), {"id": value}
    ).scalar_one_or_none()
    if exists is None:
        raise DecisionRuleError("invalid_category_id", "Unknown category.")
    return value


def _validated(payload: Mapping[str, Any]) -> dict[str, Any]:
    thresholds = {
        field: _integer(payload.get(field), field) for field in INTEGER_FIELDS
    }
    rules = payload.get("rules") or {}
    if not isinstance(rules, Mapping):
        raise DecisionRuleError("invalid_rules", "rules must be an object.")
    rules = dict(rules)
    if rules.get("schema_version") != 1:
        raise DecisionRuleError(
            "invalid_rules", "rules.schema_version must be 1."
        )
    return {
        **thresholds,
        "min_conversion_rate": _rate(payload.get("min_conversion_rate")),
        "rules": rules,
    }


def _active(session: Session, tenant: TenantContext, category_id: uuid.UUID | None):
    return session.execute(
        text(
            """
            SELECT * FROM decision_rule_sets
            WHERE is_active
              AND (
                  (CAST(:category_id AS uuid) IS NOT NULL AND store_id = :store_id
                   AND category_id = CAST(:category_id AS uuid))
                  OR (CAST(:category_id AS uuid) IS NULL AND store_id = :store_id
                      AND category_id IS NULL)
              )
            ORDER BY version DESC
            LIMIT 1
            """
        ),
        {"store_id": tenant.store_id, "category_id": category_id},
    ).mappings().one_or_none()


def _out(row: Mapping[str, Any], scope: str) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "scope": scope,
        "store_id": str(row["store_id"]) if row["store_id"] else None,
        "category_id": (
            str(row["category_id"]) if row["category_id"] else None
        ),
        "version": row["version"],
        "is_active": row["is_active"],
        "min_spend_minor": row["min_spend_minor"],
        "min_clicks": row["min_clicks"],
        "min_conversions": row["min_conversions"],
        "min_confirmed_deposits": row["min_confirmed_deposits"],
        "min_conversion_rate": (
            float(row["min_conversion_rate"])
            if row["min_conversion_rate"] is not None
            else None
        ),
        "max_cost_per_conversion_minor": row[
            "max_cost_per_conversion_minor"
        ],
        "rules": row["rules"],
        "created_by": str(row["created_by"]) if row["created_by"] else None,
        "created_at": row["created_at"].isoformat(),
    }


def upsert_rule_set(
    session: Session, tenant: TenantContext, payload: Mapping[str, Any]
) -> dict[str, Any]:
    category_id = _category(session, payload.get("category_id"))
    data = _validated(payload)
    previous = _active(session, tenant, category_id)

    version = session.execute(
        text(
            """
            SELECT COALESCE(MAX(version), 0) + 1 FROM decision_rule_sets
            WHERE store_id = :store_id
              AND (
                  (CAST(:category_id AS uuid) IS NULL AND category_id IS NULL)
                  OR category_id = CAST(:category_id AS uuid)
              )
            """
        ),
        {"store_id": tenant.store_id, "category_id": category_id},
    ).scalar_one()
    session.execute(
        text(
            """
            UPDATE decision_rule_sets SET is_active = false
            WHERE store_id = :store_id AND is_active
              AND (
                  (CAST(:category_id AS uuid) IS NULL AND category_id IS NULL)
                  OR category_id = CAST(:category_id AS uuid)
              )
            """
        ),
        {"store_id": tenant.store_id, "category_id": category_id},
    )
    row = session.execute(
        text(
            """
            INSERT INTO decision_rule_sets (
                store_id, category_id, version, is_active,
                min_spend_minor, min_clicks, min_conversions,
                min_confirmed_deposits, min_conversion_rate,
                max_cost_per_conversion_minor, rules, created_by
            ) VALUES (
                :store_id, :category_id, :version, true,
                :min_spend_minor, :min_clicks, :min_conversions,
                :min_confirmed_deposits, :min_conversion_rate,
                :max_cost_per_conversion_minor, :rules, :created_by
            )
            RETURNING *
            """
        ),
        {
            "store_id": tenant.store_id,
            "category_id": category_id,
            "version": version,
            "min_spend_minor": data["min_spend_minor"] or 0,
            "min_clicks": data["min_clicks"] or 0,
            "min_conversions": data["min_conversions"] or 0,
            "min_confirmed_deposits": data["min_confirmed_deposits"] or 0,
            "min_conversion_rate": data["min_conversion_rate"],
            "max_cost_per_conversion_minor": data[
                "max_cost_per_conversion_minor"
            ],
            "rules": Jsonb(data["rules"]),
            "created_by": tenant.user_id,
        },
    ).mappings().one()

    AuditService(session, tenant).record(
        action="decision_rule_set.updated",
        target_type="decision_rule_set",
        target_id=row["id"],
        before=(
            {
                "version": previous["version"],
                "is_active": previous["is_active"],
                "min_conversion_rate": (
                    float(previous["min_conversion_rate"])
                    if previous["min_conversion_rate"] is not None
                    else None
                ),
                "max_cost_per_conversion_minor": previous[
                    "max_cost_per_conversion_minor"
                ],
            }
            if previous is not None
            else None
        ),
        after={
            "version": row["version"],
            "is_active": True,
            "min_conversion_rate": data["min_conversion_rate"],
            "max_cost_per_conversion_minor": data[
                "max_cost_per_conversion_minor"
            ],
        },
    )
    return _out(row, "category" if category_id else "store")


def list_rule_sets(
    session: Session, tenant: TenantContext, category_id: object = None
) -> list[dict[str, Any]]:
    category = _category(session, category_id)
    rows = session.execute(
        text(
            """
            SELECT * FROM decision_rule_sets
            WHERE store_id = :store_id
              AND (
                  (CAST(:category_id AS uuid) IS NULL AND category_id IS NULL)
                  OR category_id = CAST(:category_id AS uuid)
              )
            ORDER BY version DESC
            """
        ),
        {"store_id": tenant.store_id, "category_id": category},
    ).mappings().all()
    scope = "category" if category else "store"
    return [_out(row, scope) for row in rows]


def resolve_rule_set(
    session: Session, tenant: TenantContext, category_id: object = None
) -> dict[str, Any] | None:
    category = _category(session, category_id)
    if category is not None:
        row = _active(session, tenant, category)
        if row is not None:
            return _out(row, "category")
    row = _active(session, tenant, None)
    if row is not None:
        return _out(row, "store")
    platform = session.execute(
        text(
            """
            SELECT * FROM decision_rule_sets
            WHERE store_id IS NULL AND category_id IS NULL AND is_active
            ORDER BY version DESC
            LIMIT 1
            """
        )
    ).mappings().one_or_none()
    return _out(platform, "platform") if platform is not None else None


__all__ = [
    "DecisionRuleError",
    "list_rule_sets",
    "resolve_rule_set",
    "upsert_rule_set",
]
