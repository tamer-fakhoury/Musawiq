"""Audit list scoping, filters, pagination, and direct RLS."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import psycopg

from scripts.gen_schema_docs import libpq_url


def _headers(
    store_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    role: str = "owner",
    correlation_id: uuid.UUID | None = None,
) -> dict[str, str]:
    values = {
        "X-Store-Id": str(store_id),
        "X-User-Id": str(user_id),
        "X-User-Role": role,
    }
    if correlation_id is not None:
        values["X-Correlation-Id"] = str(correlation_id)
    return values


def _write(
    client,
    *,
    store: uuid.UUID,
    user: uuid.UUID,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
    role: str = "owner",
    before=None,
    after=None,
) -> None:
    response = client.post(
        "/_test/audit-write",
        headers=_headers(store, user, role=role),
        json={
            "action": action,
            "target_type": target_type,
            "target_id": str(target_id),
            "before": before,
            "after": after,
        },
    )
    assert response.status_code == 200


def test_each_store_sees_only_its_own_logs(client, seed) -> None:
    action = f"probe.scope.{uuid.uuid4().hex}"
    target_a, target_b = uuid.uuid4(), uuid.uuid4()
    _write(
        client,
        store=seed.store_a,
        user=seed.user_a,
        action=action,
        target_type="probe",
        target_id=target_a,
    )
    _write(
        client,
        store=seed.store_b,
        user=seed.user_b,
        action=action,
        target_type="probe",
        target_id=target_b,
    )

    page_a = client.get(
        "/audit-logs",
        headers=_headers(seed.store_a, seed.user_a),
        params={"action": action},
    )
    page_b = client.get(
        "/audit-logs",
        headers=_headers(seed.store_b, seed.user_b),
        params={"action": action},
    )

    assert page_a.status_code == 200
    assert page_b.status_code == 200
    assert page_a.json()["total"] == 1
    assert page_b.json()["total"] == 1
    assert page_a.json()["items"][0]["target_id"] == str(target_a)
    assert page_b.json()["items"][0]["target_id"] == str(target_b)
    assert all(
        item["store_id"] == str(seed.store_a)
        for item in page_a.json()["items"]
    )
    assert all(
        item["store_id"] == str(seed.store_b)
        for item in page_b.json()["items"]
    )


def test_direct_rls_hides_the_other_store(client, seed, scratch) -> None:
    action = f"probe.rls.{uuid.uuid4().hex}"
    _write(
        client,
        store=seed.store_a,
        user=seed.user_a,
        action=action,
        target_type="probe",
        target_id=uuid.uuid4(),
    )
    _write(
        client,
        store=seed.store_b,
        user=seed.user_b,
        action=action,
        target_type="probe",
        target_id=uuid.uuid4(),
    )

    with psycopg.connect(libpq_url(scratch.url)) as conn:
        with conn.transaction():
            conn.execute(
                "SELECT set_config('app.store_id', %s, true)",
                (str(seed.store_b),),
            )
            rows = conn.execute(
                "SELECT store_id FROM public.audit_logs WHERE action = %s",
                (action,),
            ).fetchall()
            assert rows
            assert {row[0] for row in rows} == {seed.store_b}

        with conn.transaction():
            conn.execute(
                "SELECT set_config('app.store_id', %s, true)",
                (str(seed.store_a),),
            )
            rows = conn.execute(
                "SELECT store_id FROM public.audit_logs WHERE action = %s",
                (action,),
            ).fetchall()
            assert rows
            assert {row[0] for row in rows} == {seed.store_a}


def test_filters_by_target_and_date_range(client, seed) -> None:
    action = f"probe.filters.{uuid.uuid4().hex}"
    target_one, target_two = uuid.uuid4(), uuid.uuid4()
    for target in (target_one, target_two):
        _write(
            client,
            store=seed.store_a,
            user=seed.user_a,
            action=action,
            target_type="probe_filter",
            target_id=target,
        )

    now = datetime.now(timezone.utc)
    base_params = {
        "action": action,
        "target_type": "probe_filter",
    }
    by_target = client.get(
        "/audit-logs",
        headers=_headers(seed.store_a, seed.user_a),
        params={**base_params, "target_id": str(target_one)},
    )
    assert by_target.status_code == 200
    assert by_target.json()["total"] == 1
    assert by_target.json()["items"][0]["target_id"] == str(target_one)

    in_range = client.get(
        "/audit-logs",
        headers=_headers(seed.store_a, seed.user_a),
        params={
            **base_params,
            "date_from": (now - timedelta(hours=1)).isoformat(),
            "date_to": (now + timedelta(hours=1)).isoformat(),
        },
    )
    assert in_range.status_code == 200
    assert in_range.json()["total"] == 2

    future_only = client.get(
        "/audit-logs",
        headers=_headers(seed.store_a, seed.user_a),
        params={
            **base_params,
            "date_from": (now + timedelta(hours=1)).isoformat(),
        },
    )
    assert future_only.status_code == 200
    assert future_only.json()["total"] == 0

    past_only = client.get(
        "/audit-logs",
        headers=_headers(seed.store_a, seed.user_a),
        params={
            **base_params,
            "date_to": (now - timedelta(hours=1)).isoformat(),
        },
    )
    assert past_only.status_code == 200
    assert past_only.json()["total"] == 0


def test_filters_by_actor_user(client, seed) -> None:
    action = f"probe.actor.{uuid.uuid4().hex}"
    _write(
        client,
        store=seed.store_a,
        user=seed.user_a,
        action=action,
        target_type="probe_actor",
        target_id=uuid.uuid4(),
    )

    own = client.get(
        "/audit-logs",
        headers=_headers(seed.store_a, seed.user_a),
        params={"action": action, "actor_user_id": str(seed.user_a)},
    )
    other = client.get(
        "/audit-logs",
        headers=_headers(seed.store_a, seed.user_a),
        params={"action": action, "actor_user_id": str(seed.user_b)},
    )

    assert own.status_code == 200
    assert other.status_code == 200
    assert own.json()["total"] == 1
    assert other.json()["total"] == 0


def test_invalid_date_range_returns_422(client, seed) -> None:
    now = datetime.now(timezone.utc)
    response = client.get(
        "/audit-logs",
        headers=_headers(seed.store_a, seed.user_a),
        params={
            "date_from": (now + timedelta(hours=1)).isoformat(),
            "date_to": (now - timedelta(hours=1)).isoformat(),
        },
    )
    assert response.status_code == 422


def test_pagination(client, seed) -> None:
    action = f"probe.pagination.{uuid.uuid4().hex}"
    for _ in range(3):
        _write(
            client,
            store=seed.store_a,
            user=seed.user_a,
            action=action,
            target_type="probe_page",
            target_id=uuid.uuid4(),
        )

    first = client.get(
        "/audit-logs",
        headers=_headers(seed.store_a, seed.user_a),
        params={"action": action, "limit": 2, "offset": 0},
    )
    second = client.get(
        "/audit-logs",
        headers=_headers(seed.store_a, seed.user_a),
        params={"action": action, "limit": 2, "offset": 2},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["total"] == 3
    assert second.json()["total"] == 3
    assert len(first.json()["items"]) == 2
    assert len(second.json()["items"]) == 1


def test_analyst_can_read_but_not_export(client, seed) -> None:
    response = client.get(
        "/audit-logs",
        headers=_headers(seed.store_a, seed.user_a, role="analyst"),
    )
    assert response.status_code == 200

    export = client.get(
        "/audit-logs/export.csv",
        headers=_headers(seed.store_a, seed.user_a, role="analyst"),
    )
    assert export.status_code == 403
    body = export.json()
    error = body.get("error") or body.get("detail", {}).get("error", {})
    assert error.get("code") in {"forbidden", "permission_denied"}
