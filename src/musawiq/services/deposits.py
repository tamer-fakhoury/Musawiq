"""Deposit recording and manual confirmation (FR-4.1.5)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.services.audit import AuditService

DEPOSIT_STATES = frozenset({"pending", "confirmed", "rejected"})
TERMINAL_STATES = frozenset({"confirmed", "rejected"})


class DepositError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _uuid(value: object, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise DepositError(f"invalid_{name}", f"{name} must be a UUID.") from exc


def _order(session: Session, tenant: TenantContext, order_id: object):
    row = session.execute(
        text(
            "SELECT * FROM orders WHERE id = :id AND store_id = :store_id"
        ),
        {"id": _uuid(order_id, "order_id"), "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise DepositError("not_found", "Order not found.", status_code=404)
    return row


def _evidence(session: Session, tenant: TenantContext, evidence_id: object):
    row = session.execute(
        text(
            "SELECT id, purpose, status FROM stored_files "
            "WHERE id = :id AND store_id = :store_id"
        ),
        {
            "id": _uuid(evidence_id, "evidence_file_id"),
            "store_id": tenant.store_id,
        },
    ).mappings().one_or_none()
    if row is None:
        raise DepositError(
            "invalid_evidence", "Evidence file must belong to the store."
        )
    if row["purpose"] != "deposit_evidence":
        raise DepositError(
            "invalid_evidence",
            "Evidence file purpose must be deposit_evidence.",
        )
    if row["status"] == "deleted":
        raise DepositError("invalid_evidence", "Evidence file was deleted.")
    return row["id"]


def _validate(
    session: Session,
    tenant: TenantContext,
    order: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    status = payload.get("status")
    if status not in DEPOSIT_STATES:
        raise DepositError(
            "invalid_status", "status must be pending, confirmed, or rejected."
        )
    method = payload.get("method") or "manual"
    if method == "payment_gateway":
        raise DepositError(
            "gateway_not_supported",
            "Payment-gateway deposits are deferred to Phase 2 (decision D2).",
        )
    if method != "manual":
        raise DepositError("invalid_method", "method must be manual.")

    amount = payload.get("amount_minor", order["total_minor"])
    if (
        not isinstance(amount, int)
        or isinstance(amount, bool)
        or amount <= 0
    ):
        raise DepositError(
            "invalid_amount", "amount_minor must be a positive integer."
        )
    currency = payload.get("currency") or order["currency"].strip()
    if len(str(currency)) != 3:
        raise DepositError("invalid_currency", "currency must be ISO 4217.")

    evidence_id = None
    if status == "confirmed":
        if payload.get("evidence_file_id") is None:
            raise DepositError(
                "evidence_required",
                "Manual confirmation requires an evidence file.",
            )
        evidence_id = _evidence(
            session, tenant, payload.get("evidence_file_id")
        )
    elif payload.get("evidence_file_id") is not None:
        evidence_id = _evidence(
            session, tenant, payload.get("evidence_file_id")
        )
    return {
        "status": status,
        "method": "manual",
        "amount": amount,
        "currency": str(currency),
        "evidence_id": evidence_id,
        "external_payment_id": payload.get("external_payment_id"),
    }


def _emit_confirmed_event(
    session: Session, tenant: TenantContext, order: Mapping[str, Any], deposit_id
) -> None:
    session.execute(
        text(
            """
            INSERT INTO events (
                store_id, event_id, tracking_session_id, test_id, campaign_id,
                event_type, source, occurred_at, is_bot, properties
            ) VALUES (
                :store_id, :event_id, :session_id, :test_id, :campaign_id,
                'deposit_confirmed', 'server', now(), false, :properties
            )
            """
        ),
        {
            "store_id": tenant.store_id,
            "event_id": uuid.uuid4(),
            "session_id": order["tracking_session_id"],
            "test_id": order["test_id"],
            "campaign_id": order["campaign_id"],
            "properties": Jsonb(
                {
                    "schema_version": 1,
                    "order_id": str(order["id"]),
                    "deposit_id": str(deposit_id),
                }
            ),
        },
    )


def _audit(
    session: Session,
    tenant: TenantContext,
    *,
    action: str,
    deposit_id,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any],
) -> None:
    AuditService(session, tenant).record(
        action=action,
        target_type="deposit",
        target_id=deposit_id,
        before=dict(before) if before is not None else None,
        after=dict(after),
    )


def _out(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "order_id": str(row["order_id"]),
        "test_id": str(row["test_id"]) if row["test_id"] else None,
        "status": row["status"],
        "amount_minor": row["amount_minor"],
        "currency": row["currency"].strip(),
        "method": row["method"],
        "evidence_file_id": (
            str(row["evidence_file_id"]) if row["evidence_file_id"] else None
        ),
        "external_payment_id": row["external_payment_id"],
        "verified_by": str(row["verified_by"]) if row["verified_by"] else None,
        "verified_at": (
            row["verified_at"].isoformat() if row["verified_at"] else None
        ),
    }


def create_deposit(
    session: Session,
    tenant: TenantContext,
    order_id: object,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    order = _order(session, tenant, order_id)
    data = _validate(session, tenant, order, payload)

    verified = data["status"] == "confirmed"
    row = session.execute(
        text(
            """
            INSERT INTO deposits (
                store_id, order_id, test_id, status, amount_minor, currency,
                method, evidence_file_id, external_payment_id, verified_by,
                verified_at
            ) VALUES (
                :store_id, :order_id, :test_id, :status, :amount_minor,
                :currency, :method, :evidence_file_id, :external_payment_id,
                :verified_by, CASE WHEN :verified THEN now() ELSE NULL END
            )
            RETURNING *
            """
        ),
        {
            "store_id": tenant.store_id,
            "order_id": order["id"],
            "test_id": order["test_id"],
            "status": data["status"],
            "amount_minor": data["amount"],
            "currency": data["currency"],
            "method": data["method"],
            "evidence_file_id": data["evidence_id"],
            "external_payment_id": data["external_payment_id"],
            "verified_by": tenant.user_id if verified else None,
            "verified": verified,
        },
    ).mappings().one()

    _audit(
        session,
        tenant,
        action=f"deposit.{data['status']}",
        deposit_id=row["id"],
        before={"status": None},
        after={"status": data["status"], "order_id": str(order["id"])},
    )
    if data["status"] == "confirmed":
        _emit_confirmed_event(session, tenant, order, row["id"])
    return _out(row)


def update_deposit(
    session: Session,
    tenant: TenantContext,
    deposit_id: object,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    row = session.execute(
        text(
            "SELECT * FROM deposits WHERE id = :id AND store_id = :store_id"
        ),
        {"id": _uuid(deposit_id, "deposit_id"), "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise DepositError("not_found", "Deposit not found.", status_code=404)
    if row["status"] in TERMINAL_STATES:
        raise DepositError(
            "terminal_state",
            "Confirmed or rejected deposits cannot change.",
            status_code=409,
        )

    order = _order(session, tenant, row["order_id"])
    data = _validate(session, tenant, order, payload)
    if data["status"] == "pending":
        raise DepositError(
            "invalid_transition", "pending deposits can only be confirmed or rejected."
        )
    verified = data["status"] == "confirmed"
    updated = session.execute(
        text(
            """
            UPDATE deposits
            SET status = :status,
                amount_minor = :amount_minor,
                currency = :currency,
                method = :method,
                evidence_file_id = :evidence_file_id,
                verified_by = CASE WHEN :verified THEN :user_id ELSE verified_by END,
                verified_at = CASE WHEN :verified THEN now() ELSE verified_at END
            WHERE id = :id AND store_id = :store_id
            RETURNING *
            """
        ),
        {
            "id": row["id"],
            "store_id": tenant.store_id,
            "status": data["status"],
            "amount_minor": data["amount"],
            "currency": data["currency"],
            "method": data["method"],
            "evidence_file_id": data["evidence_id"],
            "verified": verified,
            "user_id": tenant.user_id,
        },
    ).mappings().one()

    _audit(
        session,
        tenant,
        action=f"deposit.{data['status']}",
        deposit_id=row["id"],
        before={
            "status": row["status"],
            "evidence_file_id": (
                str(row["evidence_file_id"]) if row["evidence_file_id"] else None
            ),
        },
        after={
            "status": data["status"],
            "evidence_file_id": (
                str(data["evidence_id"]) if data["evidence_id"] else None
            ),
        },
    )
    if data["status"] == "confirmed":
        _emit_confirmed_event(session, tenant, order, row["id"])
    return _out(updated)


def list_deposits(
    session: Session, tenant: TenantContext, order_id: object
) -> list[dict[str, Any]]:
    order = _order(session, tenant, order_id)
    rows = session.execute(
        text(
            "SELECT * FROM deposits WHERE order_id = :id AND store_id = :store_id "
            "ORDER BY created_at, id"
        ),
        {"id": order["id"], "store_id": tenant.store_id},
    ).mappings().all()
    return [_out(row) for row in rows]


__all__ = [
    "DEPOSIT_STATES",
    "DepositError",
    "create_deposit",
    "list_deposits",
    "update_deposit",
]
