"""FR-4.1.5: manual deposit confirmation, states, events, and audit."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import text

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _headers(site):
    return {
        "X-Store-Id": str(site.store_id),
        "X-User-Id": str(site.user_id),
        "X-User-Role": "owner",
    }


def _cod_order(client, site) -> str:
    session = client.post(
        f"/p/{site.page_slug}/track/session",
        json={"consent_state": "granted", "tk": site.tracking_token},
        headers={"User-Agent": UA},
    ).json()
    started = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=10)
    order = client.post(
        f"/p/{site.page_slug}/cod-orders",
        json={
            "session_id": session["session_id"],
            "customer_name": "Ahmed Ali",
            "customer_phone": "0512345678",
            "customer_address": "Riyadh, Al Olaya, King Fahd Road 12",
            "quantity": 1,
            "form_started_at": started.isoformat(),
        },
        headers={"User-Agent": UA},
    )
    assert order.status_code == 201
    return order.json()["order_id"]


def _evidence(db_engine, site) -> str:
    with db_engine.begin() as conn:
        return str(
            conn.execute(
                text(
                    """
                    INSERT INTO stored_files (
                        store_id, purpose, original_filename, mime_type,
                        size_bytes, checksum_sha256, storage_provider,
                        storage_key, status, uploaded_by_user_id
                    ) VALUES (
                        :store_id, 'deposit_evidence', 'receipt.pdf',
                        'application/pdf', 10, repeat('a', 64), 'local',
                        :key, 'committed', :user_id
                    )
                    RETURNING id
                    """
                ),
                {
                    "store_id": site.store_id,
                    "key": uuid.uuid4().hex,
                    "user_id": site.user_id,
                },
            ).scalar_one()
        )


def _create_deposit(client, site, order_id, payload):
    return client.post(
        f"/orders/{order_id}/deposits",
        json=payload,
        headers=_headers(site),
    )


def test_manual_confirmation_with_evidence_emits_event_and_audit(
    client, site, db_engine
):
    order_id = _cod_order(client, site)
    evidence_id = _evidence(db_engine, site)

    response = _create_deposit(
        client,
        site,
        order_id,
        {"status": "confirmed", "evidence_file_id": evidence_id},
    )

    assert response.status_code == 201
    deposit = response.json()
    assert deposit["status"] == "confirmed"
    assert deposit["method"] == "manual"
    assert deposit["evidence_file_id"] == evidence_id
    assert deposit["verified_by"] == str(site.user_id)
    assert deposit["test_id"] is not None

    with db_engine.connect() as conn:
        events = conn.execute(
            text(
                "SELECT count(*) FROM events WHERE event_type = "
                "'deposit_confirmed' AND store_id = :store_id"
            ),
            {"store_id": site.store_id},
        ).scalar_one()
        audits = conn.execute(
            text(
                "SELECT action FROM audit_logs WHERE target_id = :id "
                "ORDER BY created_at, id"
            ),
            {"id": deposit["id"]},
        ).scalars().all()
    assert events == 1
    assert audits == ["deposit.confirmed"]


def test_confirmation_requires_evidence_and_rejects_gateway(
    client, site, db_engine
):
    order_id = _cod_order(client, site)

    missing = _create_deposit(client, site, order_id, {"status": "confirmed"})
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "evidence_required"

    gateway = _create_deposit(
        client,
        site,
        order_id,
        {"status": "confirmed", "method": "payment_gateway"},
    )
    assert gateway.status_code == 422
    assert gateway.json()["error"]["code"] == "gateway_not_supported"

    with db_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM deposits WHERE order_id = :id"),
            {"id": order_id},
        ).scalar_one()
    assert count == 0


def test_pending_and_rejected_are_not_confirmed(client, site, db_engine):
    order_id = _cod_order(client, site)

    pending = _create_deposit(client, site, order_id, {"status": "pending"})
    assert pending.status_code == 201
    assert pending.json()["status"] == "pending"

    rejected = client.patch(
        f"/deposits/{pending.json()['id']}",
        json={"status": "rejected"},
        headers=_headers(site),
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    with db_engine.connect() as conn:
        confirmed = conn.execute(
            text(
                "SELECT count(*) FROM deposits "
                "WHERE order_id = :id AND status = 'confirmed'"
            ),
            {"id": order_id},
        ).scalar_one()
    assert confirmed == 0

    evidence_id = _evidence(db_engine, site)
    confirmed_deposit = _create_deposit(
        client,
        site,
        order_id,
        {"status": "confirmed", "evidence_file_id": evidence_id},
    )
    assert confirmed_deposit.status_code == 201

    relock = client.patch(
        f"/deposits/{confirmed_deposit.json()['id']}",
        json={"status": "rejected"},
        headers=_headers(site),
    )
    assert relock.status_code == 409
    assert relock.json()["error"]["code"] == "terminal_state"
