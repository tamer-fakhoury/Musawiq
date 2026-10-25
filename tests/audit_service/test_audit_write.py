"""Audit writes capture the request context and never store a raw IP."""

from __future__ import annotations

import uuid

import psycopg

from scripts.gen_schema_docs import libpq_url


def _headers(
    store_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    correlation_id: uuid.UUID | None = None,
    ip_hash: str | None = None,
    raw_ip: str | None = None,
) -> dict[str, str]:
    values = {
        "X-Store-Id": str(store_id),
        "X-User-Id": str(user_id),
        "X-User-Role": "owner",
    }
    if correlation_id is not None:
        values["X-Correlation-Id"] = str(correlation_id)
    if ip_hash is not None:
        values["X-IP-Hash"] = ip_hash
    if raw_ip is not None:
        values["X-Forwarded-For"] = raw_ip
    return values


def _fetch_audit_row(scratch, target_id: uuid.UUID):
    with psycopg.connect(libpq_url(scratch.admin_url)) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT actor_user_id, actor_type, store_id, action, target_type,
                       target_id, before, after, metadata, ip_hash,
                       correlation_id
                FROM public.audit_logs
                WHERE target_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (target_id,),
            )
            return cur.fetchone()


def test_record_persists_actor_target_payload_and_correlation(
    client, seed, scratch
) -> None:
    target = uuid.uuid4()
    correlation = uuid.uuid4()
    request_headers = _headers(
        seed.store_a,
        seed.user_a,
        correlation_id=correlation,
    )

    response = client.post(
        "/_test/audit-write",
        headers=request_headers,
        json={
            "action": "probe.created",
            "target_type": "probe",
            "target_id": str(target),
            "before": {"state": "old", "count": 1},
            "after": {"state": "new", "count": 2},
            "metadata": {"note": "unit-test"},
        },
    )

    assert response.status_code == 200

    page = client.get(
        "/audit-logs",
        headers=request_headers,
        params={"target_id": str(target)},
    )
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["store_id"] == str(seed.store_a)
    assert item["actor_user_id"] == str(seed.user_a)
    assert item["actor_type"] == "user"
    assert item["action"] == "probe.created"
    assert item["target_type"] == "probe"
    assert item["target_id"] == str(target)
    assert item["before"] == {"state": "old", "count": 1}
    assert item["after"] == {"state": "new", "count": 2}
    assert item["metadata"]["note"] == "unit-test"
    assert item["metadata"]["schema_version"] == 1
    assert item["correlation_id"] == str(correlation)

    row = _fetch_audit_row(scratch, target)
    assert row is not None
    assert row[0] == seed.user_a
    assert row[1] == "user"
    assert row[2] == seed.store_a
    assert row[3] == "probe.created"
    assert row[4] == "probe"
    assert row[5] == target
    assert row[6] == {"state": "old", "count": 1}
    assert row[7] == {"state": "new", "count": 2}
    assert row[8]["note"] == "unit-test"
    assert row[8]["schema_version"] == 1
    assert row[9] is None
    assert row[10] == correlation


def test_raw_ip_is_never_stored_and_supplied_hash_is_preserved(
    client, seed, scratch
) -> None:
    raw_ip_target = uuid.uuid4()
    ip_hash_target = uuid.uuid4()
    supplied_hash = "a" * 64

    raw_response = client.post(
        "/_test/audit-write",
        headers=_headers(
            seed.store_a,
            seed.user_a,
            raw_ip="203.0.113.9",
        ),
        json={
            "action": "probe.raw_ip",
            "target_type": "probe",
            "target_id": str(raw_ip_target),
        },
    )
    assert raw_response.status_code == 200
    raw_row = _fetch_audit_row(scratch, raw_ip_target)
    assert raw_row is not None
    assert raw_row[9] is None
    assert "203.0.113.9" not in str(raw_row)

    hash_response = client.post(
        "/_test/audit-write",
        headers=_headers(
            seed.store_a,
            seed.user_a,
            ip_hash=supplied_hash,
        ),
        json={
            "action": "probe.ip_hash",
            "target_type": "probe",
            "target_id": str(ip_hash_target),
        },
    )
    assert hash_response.status_code == 200
    hash_row = _fetch_audit_row(scratch, ip_hash_target)
    assert hash_row is not None
    assert hash_row[9] == supplied_hash
