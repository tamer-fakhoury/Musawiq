"""Deterministic verdict classification from snapshots and rule sets (FR-5.1.4)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.services.attribution import attribution_coverage
from musawiq.services.decision_rules import resolve_rule_set

DEFAULT_ATTRIBUTION_COVERAGE_MIN = 0.8


class VerdictError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _test(session: Session, tenant: TenantContext, test_id: object):
    try:
        test_uuid = uuid.UUID(str(test_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise VerdictError("invalid_test_id", "test_id must be a UUID.") from exc
    row = session.execute(
        text("SELECT * FROM tests WHERE id = :id AND store_id = :store_id"),
        {"id": test_uuid, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise VerdictError("not_found", "Test not found.", status_code=404)
    return row


def evaluate(
    snapshot: Mapping[str, Any],
    rule_set: Mapping[str, Any],
    *,
    tracking_events: int | None = None,
    attribution_coverage_value: float | None = None,
) -> dict[str, Any]:
    """Pure, deterministic rule evaluation; no randomness or clock access."""
    trace: list[dict[str, Any]] = []
    limitations: list[str] = []

    def record(rule: str, threshold: Any, observed: Any, passed: bool) -> bool:
        trace.append(
            {
                "rule": rule,
                "threshold": threshold,
                "observed": observed,
                "passed": passed,
            }
        )
        return passed

    completeness = float(snapshot["data_completeness"])
    sufficiency_ok = record(
        "data_completeness", 1.0, completeness, completeness >= 1.0
    )
    if not sufficiency_ok:
        limitations.append(
            f"data completeness is {completeness}, expected 1.0"
        )

    if tracking_events is not None:
        tracked = int(tracking_events)
        tracking_ok = record("tracking_events", 1, tracked, tracked > 0)
        if not tracking_ok:
            sufficiency_ok = False
            limitations.append("no tracking events were recorded")

    if attribution_coverage_value is not None:
        coverage = float(attribution_coverage_value)
        coverage_threshold = float(
            (rule_set.get("rules") or {}).get(
                "min_attribution_coverage",
                DEFAULT_ATTRIBUTION_COVERAGE_MIN,
            )
        )
        coverage_ok = record(
            "min_attribution_coverage",
            coverage_threshold,
            coverage,
            coverage >= coverage_threshold,
        )
        if not coverage_ok:
            sufficiency_ok = False
            limitations.append(
                f"attribution coverage is {coverage:.2%}, below the "
                f"minimum {coverage_threshold:.2%}"
            )

    for field, observed_field in (
        ("min_spend_minor", "spend_minor"),
        ("min_clicks", "clicks"),
        ("min_conversions", "tracked_conversions"),
        ("min_confirmed_deposits", "confirmed_deposits"),
    ):
        threshold = int(rule_set[field] or 0)
        observed = int(snapshot[observed_field])
        passed = record(field, threshold, observed, observed >= threshold)
        if not passed:
            sufficiency_ok = False
            limitations.append(
                f"{observed_field} {observed} is below the minimum {threshold}"
            )

    rate_threshold = rule_set.get("min_conversion_rate")
    rate = snapshot.get("conversion_rate")
    rate_passed = True
    if rate_threshold is not None:
        if rate is None:
            rate_passed = record("min_conversion_rate", rate_threshold, None, False)
            limitations.append("conversion rate is unavailable")
        else:
            rate_passed = record(
                "min_conversion_rate",
                float(rate_threshold),
                float(rate),
                float(rate) >= float(rate_threshold),
            )

    cost_threshold = rule_set.get("max_cost_per_conversion_minor")
    cost = snapshot.get("cost_per_conversion_minor")
    cost_passed = True
    if cost_threshold is not None:
        if cost is None:
            cost_passed = record(
                "max_cost_per_conversion_minor", cost_threshold, None, False
            )
            limitations.append("cost per conversion is unavailable")
        else:
            cost_passed = record(
                "max_cost_per_conversion_minor",
                int(cost_threshold),
                int(cost),
                int(cost) <= int(cost_threshold),
            )

    if not sufficiency_ok:
        outcome = "extend_test"
        conclusive = False
        reason = "Insufficient data or minimum volume: " + "; ".join(
            limitations
        )
    elif rate_threshold is None and cost_threshold is None:
        outcome = "extend_test"
        conclusive = False
        limitations.append("rule set defines no performance thresholds")
        reason = "Rule set is not specific enough for a conclusive verdict."
    elif rate_passed and cost_passed:
        outcome = "go"
        conclusive = True
        reason = "All performance thresholds were met."
    else:
        outcome = "no_go"
        conclusive = True
        failures = [
            item["rule"] for item in trace if not item["passed"]
        ]
        reason = "Failed performance thresholds: " + ", ".join(failures)

    return {
        "outcome": outcome,
        "is_conclusive": conclusive,
        "primary_reason": reason,
        "limitations": {
            "schema_version": 1,
            "items": limitations,
        },
        "rule_trace": {
            "schema_version": 1,
            "rule_set": {
                "id": str(rule_set["id"]),
                "scope": rule_set["scope"],
                "version": rule_set["version"],
            },
            "checks": trace,
        },
    }


def evaluate_verdict(
    session: Session,
    tenant: TenantContext,
    test_id: object,
    *,
    snapshot_id: object = None,
    extra_trace: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    test = _test(session, tenant, test_id)
    if snapshot_id is not None:
        snapshot = session.execute(
            text(
                "SELECT * FROM test_result_snapshots "
                "WHERE id = :id AND test_id = :test_id AND store_id = :store_id"
            ),
            {
                "id": uuid.UUID(str(snapshot_id)),
                "test_id": test["id"],
                "store_id": tenant.store_id,
            },
        ).mappings().one_or_none()
    else:
        snapshot = session.execute(
            text(
                "SELECT * FROM test_result_snapshots WHERE store_id = :store_id "
                "AND test_id = :test_id ORDER BY captured_at DESC, id DESC LIMIT 1"
            ),
            {"store_id": tenant.store_id, "test_id": test["id"]},
        ).mappings().one_or_none()
    if snapshot is None:
        raise VerdictError(
            "no_snapshot",
            "A result snapshot is required before evaluating a verdict.",
            status_code=409,
        )
    category_id = session.execute(
        text(
            "SELECT category_id FROM product_concepts WHERE id = :id"
        ),
        {"id": test["product_concept_id"]},
    ).scalar_one()
    rule_set = resolve_rule_set(session, tenant, category_id)
    if rule_set is None:
        raise VerdictError(
            "rule_set_required",
            "Configure a decision rule set before evaluating a verdict.",
            status_code=409,
        )

    tracking_events = session.execute(
        text(
            "SELECT count(*) FROM events "
            "WHERE store_id = :store_id AND test_id = :test_id "
            "AND occurred_at >= :start AND occurred_at < :end"
        ),
        {
            "store_id": tenant.store_id,
            "test_id": test["id"],
            "start": snapshot["period_start"],
            "end": snapshot["period_end"],
        },
    ).scalar_one()
    coverage = attribution_coverage(
        session,
        tenant.store_id,
        test_id=test["id"],
        since=snapshot["period_start"],
        until=snapshot["period_end"],
    )
    result = evaluate(
        snapshot,
        rule_set,
        tracking_events=tracking_events,
        attribution_coverage_value=coverage["coverage_percentage"] / 100,
    )
    if extra_trace:
        result["rule_trace"].update(extra_trace)
    row = session.execute(
        text(
            """
            INSERT INTO verdicts (
                store_id, test_id, result_snapshot_id, decision_rule_set_id,
                outcome, is_conclusive, primary_reason, limitations, rule_trace
            ) VALUES (
                :store_id, :test_id, :snapshot_id, :rule_set_id,
                :outcome, :is_conclusive, :primary_reason, :limitations,
                :rule_trace
            )
            RETURNING *
            """
        ),
        {
            "store_id": tenant.store_id,
            "test_id": test["id"],
            "snapshot_id": snapshot["id"],
            "rule_set_id": rule_set["id"],
            "outcome": result["outcome"],
            "is_conclusive": result["is_conclusive"],
            "primary_reason": result["primary_reason"],
            "limitations": Jsonb(result["limitations"]),
            "rule_trace": Jsonb(result["rule_trace"]),
        },
    ).mappings().one()

    next_status = "completed" if result["outcome"] in {"go", "no_go"} else "extended"
    session.execute(
        text(
            "UPDATE tests SET status = :status WHERE id = :id AND store_id = :store_id"
        ),
        {"status": next_status, "id": test["id"], "store_id": tenant.store_id},
    )
    return {
        "id": str(row["id"]),
        "test_id": str(row["test_id"]),
        "result_snapshot_id": str(row["result_snapshot_id"]),
        "decision_rule_set_id": str(row["decision_rule_set_id"]),
        "rule_set_version": rule_set["version"],
        "active_rule_set": {
            "id": rule_set["id"],
            "scope": rule_set["scope"],
            "version": rule_set["version"],
            "min_spend_minor": rule_set["min_spend_minor"],
            "min_clicks": rule_set["min_clicks"],
            "min_conversions": rule_set["min_conversions"],
            "min_confirmed_deposits": rule_set["min_confirmed_deposits"],
            "min_conversion_rate": rule_set["min_conversion_rate"],
            "max_cost_per_conversion_minor": rule_set[
                "max_cost_per_conversion_minor"
            ],
        },
        "outcome": row["outcome"],
        "is_conclusive": row["is_conclusive"],
        "primary_reason": row["primary_reason"],
        "limitations": row["limitations"],
        "rule_trace": row["rule_trace"],
        "test_status": next_status,
        "created_at": row["created_at"].isoformat(),
    }


def list_verdicts(
    session: Session, tenant: TenantContext, test_id: object
) -> list[dict[str, Any]]:
    test = _test(session, tenant, test_id)
    rows = session.execute(
        text(
            "SELECT * FROM verdicts WHERE test_id = :id AND store_id = :store_id "
            "ORDER BY created_at DESC, id DESC"
        ),
        {"id": test["id"], "store_id": tenant.store_id},
    ).mappings().all()
    return [
        {
            "id": str(row["id"]),
            "test_id": str(row["test_id"]),
            "result_snapshot_id": str(row["result_snapshot_id"]),
            "decision_rule_set_id": str(row["decision_rule_set_id"]),
            "outcome": row["outcome"],
            "is_conclusive": row["is_conclusive"],
            "primary_reason": row["primary_reason"],
            "limitations": row["limitations"],
            "rule_trace": row["rule_trace"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


__all__ = [
    "VerdictError",
    "evaluate",
    "evaluate_verdict",
    "list_verdicts",
]
