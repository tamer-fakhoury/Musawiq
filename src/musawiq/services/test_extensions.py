"""Test extension with budget caps and verdict recomputation (FR-5.1.7)."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.services.audit import AuditService
from musawiq.services.verdict_evaluation import evaluate_verdict
from musawiq.services.verdicts import compute_snapshot

RECOMPUTE_POLICIES = frozenset({"combined", "new_window"})


class ExtensionError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _parse(value: object, name: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ExtensionError(
            "invalid_window", f"{name} must be an ISO-8601 timestamp."
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _test(session: Session, tenant: TenantContext, test_id: object):
    try:
        test_uuid = uuid.UUID(str(test_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ExtensionError("invalid_test_id", "test_id must be a UUID.") from exc
    row = session.execute(
        text("SELECT * FROM tests WHERE id = :id AND store_id = :store_id"),
        {"id": test_uuid, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise ExtensionError("not_found", "Test not found.", status_code=404)
    return row


def _approver(session: Session, approved_by: object) -> uuid.UUID:
    user_id = uuid.UUID(str(approved_by))
    row = session.execute(
        text("SELECT role, status FROM users WHERE id = :id"), {"id": user_id}
    ).mappings().one_or_none()
    if row is None or row["status"] != "active":
        raise ExtensionError("invalid_approver", "Approver must be active.")
    if row["role"] not in {"owner", "manager"}:
        raise ExtensionError(
            "approval_forbidden",
            "Only an owner or manager can extend a test.",
            status_code=403,
        )
    return user_id


def _caps(session: Session, tenant: TenantContext, test_id: uuid.UUID):
    return session.execute(
        text(
            """
            SELECT total_cap_minor, daily_cap_minor, currency
            FROM budget_policies
            WHERE store_id = :store_id AND is_active AND enforcement = 'hard'
              AND (
                  test_id = :test_id
                  OR campaign_id IN (
                      SELECT id FROM campaigns
                      WHERE test_id = :test_id AND store_id = :store_id
                  )
              )
            """
        ),
        {"store_id": tenant.store_id, "test_id": test_id},
    ).mappings().all()


def extend_test(
    session: Session,
    tenant: TenantContext,
    test_id: object,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    test = _test(session, tenant, test_id)

    latest = session.execute(
        text(
            "SELECT outcome FROM verdicts WHERE test_id = :test_id "
            "AND store_id = :store_id ORDER BY created_at DESC, id DESC LIMIT 1"
        ),
        {"test_id": test["id"], "store_id": tenant.store_id},
    ).scalar_one_or_none()
    if latest != "extend_test":
        raise ExtensionError(
            "not_extendable",
            "Only tests whose latest verdict is extend_test can be extended.",
            status_code=409,
        )

    new_end = _parse(payload.get("new_end_at"), "new_end_at")
    previous_end = test["planned_end_at"]
    if new_end <= previous_end:
        raise ExtensionError(
            "invalid_window", "new_end_at must be after the current end."
        )
    added = payload.get("added_budget_minor")
    if not isinstance(added, int) or isinstance(added, bool) or added <= 0:
        raise ExtensionError(
            "invalid_budget", "added_budget_minor must be a positive integer."
        )
    policy = payload.get("recompute_policy") or "combined"
    if policy not in RECOMPUTE_POLICIES:
        raise ExtensionError(
            "invalid_policy",
            "recompute_policy must be combined or new_window.",
        )
    approved_by = _approver(
        session, payload.get("approved_by") or tenant.user_id
    )

    new_total = int(test["total_budget_minor"]) + added
    caps = _caps(session, tenant, test["id"])
    for cap in caps:
        if cap["currency"].strip() != test["currency"].strip():
            continue
        if new_total > cap["total_cap_minor"]:
            raise ExtensionError(
                "budget_cap_exceeded",
                f"Total budget {new_total} exceeds the cap "
                f"{cap['total_cap_minor']}.",
            )
        extension_days = max(
            1.0, (new_end - previous_end).total_seconds() / 86400
        )
        if added / extension_days > cap["daily_cap_minor"]:
            raise ExtensionError(
                "budget_cap_exceeded",
                "Added budget per extension day exceeds the daily cap.",
            )
    if not caps and added > int(test["total_budget_minor"]):
        raise ExtensionError(
            "budget_cap_exceeded",
            "Added budget cannot exceed the test's current total budget.",
        )

    row = session.execute(
        text(
            """
            INSERT INTO test_extensions (
                store_id, test_id, previous_end_at, new_end_at,
                added_budget_minor, currency, reason, approved_by
            ) VALUES (
                :store_id, :test_id, :previous_end_at, :new_end_at,
                :added_budget_minor, :currency, :reason, :approved_by
            )
            RETURNING *
            """
        ),
        {
            "store_id": tenant.store_id,
            "test_id": test["id"],
            "previous_end_at": previous_end,
            "new_end_at": new_end,
            "added_budget_minor": added,
            "currency": test["currency"].strip(),
            "reason": payload.get("reason"),
            "approved_by": approved_by,
        },
    ).mappings().one()

    session.execute(
        text(
            """
            UPDATE tests
            SET status = 'extended',
                planned_end_at = :new_end,
                total_budget_minor = :new_total
            WHERE id = :id AND store_id = :store_id
            """
        ),
        {
            "new_end": new_end,
            "new_total": new_total,
            "id": test["id"],
            "store_id": tenant.store_id,
        },
    )
    AuditService(session, tenant).record(
        action="test.extended",
        target_type="test",
        target_id=test["id"],
        before={
            "planned_end_at": previous_end.isoformat(),
            "total_budget_minor": int(test["total_budget_minor"]),
        },
        after={
            "planned_end_at": new_end.isoformat(),
            "total_budget_minor": new_total,
            "recompute_policy": policy,
        },
    )

    window_start = (
        test["planned_start_at"] if policy == "combined" else previous_end
    )
    snapshot = compute_snapshot(
        session,
        tenant,
        test["id"],
        {
            "period_start": window_start.isoformat(),
            "period_end": new_end.isoformat(),
        },
    )
    verdict = evaluate_verdict(
        session,
        tenant,
        test["id"],
        snapshot_id=snapshot["id"],
        extra_trace={"recompute_policy": policy},
    )
    return {
        "id": str(row["id"]),
        "test_id": str(row["test_id"]),
        "previous_end_at": row["previous_end_at"].isoformat(),
        "new_end_at": row["new_end_at"].isoformat(),
        "added_budget_minor": row["added_budget_minor"],
        "currency": row["currency"].strip(),
        "reason": row["reason"],
        "approved_by": str(row["approved_by"]),
        "recompute_policy": policy,
        "snapshot_id": snapshot["id"],
        "verdict_outcome": verdict["outcome"],
        "verdict_id": verdict["id"],
        "test_status": verdict["test_status"],
    }


def list_extensions(
    session: Session, tenant: TenantContext, test_id: object
) -> list[dict[str, Any]]:
    test = _test(session, tenant, test_id)
    rows = session.execute(
        text(
            "SELECT * FROM test_extensions WHERE test_id = :id "
            "AND store_id = :store_id ORDER BY created_at, id"
        ),
        {"id": test["id"], "store_id": tenant.store_id},
    ).mappings().all()
    return [
        {
            "id": str(row["id"]),
            "previous_end_at": row["previous_end_at"].isoformat(),
            "new_end_at": row["new_end_at"].isoformat(),
            "added_budget_minor": row["added_budget_minor"],
            "currency": row["currency"].strip(),
            "reason": row["reason"],
            "approved_by": str(row["approved_by"]),
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


__all__ = [
    "ExtensionError",
    "RECOMPUTE_POLICIES",
    "extend_test",
    "list_extensions",
]
