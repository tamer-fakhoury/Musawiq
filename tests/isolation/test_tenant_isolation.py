"""Cross-store isolation through the API and repository layers."""

from __future__ import annotations

import uuid

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from musawiq.db.tenant import (
    TenantContextMissing,
    clear_tenant,
    set_local_tenant,
)
from musawiq.repositories.base import TenantScopedRepository
from scripts.gen_schema_docs import libpq_url


def _headers(
    store_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    role: str = "owner",
    correlation_id: uuid.UUID | None = None,
) -> dict[str, str]:
    headers = {
        "X-Store-Id": str(store_id),
        "X-User-Id": str(user_id),
        "X-User-Role": role,
    }
    if correlation_id is not None:
        headers["X-Correlation-Id"] = str(correlation_id)
    return headers


def test_each_tenant_sees_only_its_products_and_orders(client, seed) -> None:
    products_a = client.get(
        "/_test/products",
        headers=_headers(seed.store_a, seed.user_a),
    )
    products_b = client.get(
        "/_test/products",
        headers=_headers(seed.store_b, seed.user_b),
    )
    orders_a = client.get(
        "/_test/orders",
        headers=_headers(seed.store_a, seed.user_a),
    )
    orders_b = client.get(
        "/_test/orders",
        headers=_headers(seed.store_b, seed.user_b),
    )

    assert products_a.status_code == 200
    assert products_b.status_code == 200
    assert orders_a.status_code == 200
    assert orders_b.status_code == 200

    assert {row["id"] for row in products_a.json()} == {str(seed.product_a)}
    assert {row["id"] for row in products_b.json()} == {str(seed.product_b)}
    assert {row["id"] for row in orders_a.json()} == {str(seed.order_a)}
    assert {row["id"] for row in orders_b.json()} == {str(seed.order_b)}
    assert all(row["store_id"] == str(seed.store_a) for row in products_a.json())
    assert all(row["store_id"] == str(seed.store_b) for row in products_b.json())


def test_request_session_sets_transaction_local_tenant(client, seed) -> None:
    response = client.get(
        "/_test/tenant-settings",
        headers=_headers(seed.store_a, seed.user_a),
    )

    assert response.status_code == 200
    assert response.json() == {
        "store_id": str(seed.store_a),
        "user_id": str(seed.user_a),
    }


def test_cross_store_get_returns_404_and_audits(
    client, seed, scratch_url
) -> None:
    correlation_id = uuid.uuid4()

    response = client.get(
        f"/_test/products/{seed.product_b}",
        headers=_headers(
            seed.store_a,
            seed.user_a,
            correlation_id=correlation_id,
        ),
    )

    assert response.status_code == 404
    assert str(seed.product_b) not in response.text

    with psycopg.connect(libpq_url(scratch_url), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT store_id, actor_user_id, actor_type, action,
                       target_type, target_id, metadata, correlation_id
                FROM public.audit_logs
                WHERE action = 'security.cross_store_denied'
                  AND correlation_id = %s
                """,
                (correlation_id,),
            )
            row = cur.fetchone()

    assert row is not None
    (
        store_id,
        actor_user_id,
        actor_type,
        action,
        target_type,
        target_id,
        metadata,
        audit_correlation_id,
    ) = row
    assert store_id == seed.store_a
    assert actor_user_id == seed.user_a
    assert actor_type == "user"
    assert action == "security.cross_store_denied"
    assert target_type == "product"
    assert target_id == seed.product_b
    assert audit_correlation_id == correlation_id
    assert metadata["schema_version"] == 1
    assert metadata["target_id"] == str(seed.product_b)
    assert metadata["correlation_id"] == str(correlation_id)


def test_missing_headers_return_401(client) -> None:
    response = client.get("/_test/products")

    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "unauthorized"
    assert error["correlation_id"]


def test_malformed_headers_return_401(client, seed) -> None:
    response = client.get(
        "/_test/products",
        headers={
            "X-Store-Id": "not-a-uuid",
            "X-User-Id": str(seed.user_a),
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_repository_without_tenant_raises(scratch_url, seed) -> None:
    engine = create_engine(scratch_url)
    try:
        with engine.connect() as connection:
            session = Session(bind=connection)
            try:
                with pytest.raises(TenantContextMissing):
                    TenantScopedRepository(session, "products")

                set_local_tenant(session, seed.store_a, seed.user_a)
                repository = TenantScopedRepository(session, "products")
                clear_tenant(session)
                with pytest.raises(TenantContextMissing):
                    repository.list()
            finally:
                session.close()
                connection.rollback()
    finally:
        engine.dispose()
