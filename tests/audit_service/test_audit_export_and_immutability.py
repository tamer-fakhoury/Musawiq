"""CSV export, owner restriction, immutability, and audited mutation."""

from __future__ import annotations

import uuid

import psycopg

from musawiq.services.audit import AuditService
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
    before=None,
    after=None,
) -> None:
    response = client.post(
        "/_test/audit-write",
        headers=_headers(store, user),
        json={
            "action": action,
            "target_type": target_type,
            "target_id": str(target_id),
            "before": before,
            "after": after,
        },
    )
    assert response.status_code == 200


def test_export_is_owner_only_and_has_a_csv_header(client, seed) -> None:
    action = f"probe.export.{uuid.uuid4().hex}"
    _write(
        client,
        store=seed.store_a,
        user=seed.user_a,
        action=action,
        target_type="probe_export",
        target_id=uuid.uuid4(),
        before={"value": 1},
        after={"value": 2},
    )

    manager = client.get(
        "/audit-logs/export.csv",
        headers=_headers(seed.store_a, seed.user_a, role="manager"),
        params={"action": action},
    )
    assert manager.status_code == 403

    owner = client.get(
        "/audit-logs/export.csv",
        headers=_headers(seed.store_a, seed.user_a),
        params={"action": action},
    )
    assert owner.status_code == 200
    assert owner.headers["content-type"].startswith("text/csv")
    assert "attachment" in owner.headers["content-disposition"]
    lines = owner.text.splitlines()
    assert lines[0] == (
        "id,created_at,store_id,actor_user_id,actor_type,action,"
        "target_type,target_id,before,after,metadata,correlation_id"
    )
    assert len(lines) == 2
    assert action in lines[1]


def test_no_route_or_service_method_mutates_existing_logs(client, seed) -> None:
    for method in ("patch", "delete"):
        response = getattr(client, method)(
            "/audit-logs",
            headers=_headers(seed.store_a, seed.user_a),
        )
        assert response.status_code == 405

        response = getattr(client, method)(
            f"/audit-logs/{uuid.uuid4()}",
            headers=_headers(seed.store_a, seed.user_a),
        )
        assert response.status_code in (404, 405)

    for name in ("update", "delete", "remove"):
        assert not hasattr(AuditService, name)


def test_audited_mutation_writes_log_after_change(client, seed, scratch) -> None:
    correlation = uuid.uuid4()
    response = client.post(
        f"/_test/products/{seed.product_a}/rename",
        headers=_headers(
            seed.store_a,
            seed.user_a,
            correlation_id=correlation,
        ),
        json={"name": "Renamed Product A"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Product A"

    page = client.get(
        "/audit-logs",
        headers=_headers(seed.store_a, seed.user_a),
        params={
            "action": "product.renamed",
            "target_type": "product",
            "target_id": str(seed.product_a),
        },
    )
    assert page.status_code == 200
    assert page.json()["total"] == 1
    item = page.json()["items"][0]
    assert item["actor_user_id"] == str(seed.user_a)
    assert item["before"] == {"name": "Audit Product A"}
    assert item["after"] == {"name": "Renamed Product A"}
    assert item["correlation_id"] == str(correlation)

    with psycopg.connect(libpq_url(scratch.admin_url)) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name FROM public.products WHERE id = %s",
                (seed.product_a,),
            )
            assert cur.fetchone()[0] == "Renamed Product A"
