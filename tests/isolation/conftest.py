"""Fixtures for cross-store isolation tests.

These tests provision a disposable migrated database, seed two independent
stores, and exercise the production tenant middleware/dependencies through a
small set of test-only read routes.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

import psycopg
import pytest
from fastapi import Depends, Request
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.api.app import create_app
from musawiq.api.deps import get_owned_or_404, get_session, get_tenant
from musawiq.config import get_settings
from musawiq.db.session import dispose_engine
from musawiq.repositories.base import TenantScopedRepository
from scripts.gen_schema_docs import libpq_url
from scripts.seed_dev import scratch_database


@dataclass(frozen=True)
class SeedData:
    user_a: uuid.UUID
    user_b: uuid.UUID
    store_a: uuid.UUID
    store_b: uuid.UUID
    product_a: uuid.UUID
    product_b: uuid.UUID
    order_a: uuid.UUID
    order_b: uuid.UUID


@pytest.fixture(scope="module")
def scratch_url() -> str:
    admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
    if not admin_url:
        pytest.fail("MUSAWIQ_ADMIN_DATABASE_URL is not set")
    with scratch_database(admin_url) as url:
        yield url


@pytest.fixture(scope="module")
def seed(scratch_url: str) -> SeedData:
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    store_a, store_b = uuid.uuid4(), uuid.uuid4()
    product_a, product_b = uuid.uuid4(), uuid.uuid4()
    order_a, order_b = uuid.uuid4(), uuid.uuid4()

    with psycopg.connect(libpq_url(scratch_url), autocommit=True) as conn:
        with conn.cursor() as cur:
            for user_id, email, name in (
                (user_a, f"owner-a-{user_a.hex}@dev.local", "Owner A"),
                (user_b, f"owner-b-{user_b.hex}@dev.local", "Owner B"),
            ):
                cur.execute(
                    """
                    INSERT INTO public.users (
                        id, email, full_name, role, status
                    ) VALUES (%s, %s, %s, 'owner', 'active')
                    """,
                    (user_id, email, name),
                )

            for store_id, user_id, name, slug in (
                (store_a, user_a, "Store A", f"store-a-{store_a.hex}"),
                (store_b, user_b, "Store B", f"store-b-{store_b.hex}"),
            ):
                cur.execute(
                    """
                    INSERT INTO public.stores (
                        id, owner_user_id, name, slug, status,
                        default_currency, default_language, timezone,
                        country_code, onboarding_status
                    ) VALUES (
                        %s, %s, %s, %s, 'active', 'SAR', 'ar',
                        'Asia/Riyadh', 'SA', 'completed'
                    )
                    """,
                    (store_id, user_id, name, slug),
                )

            for product_id, store_id, name in (
                (product_a, store_a, "Product A"),
                (product_b, store_b, "Product B"),
            ):
                cur.execute(
                    """
                    INSERT INTO public.products (
                        id, store_id, name, currency, source
                    ) VALUES (%s, %s, %s, 'SAR', 'manual')
                    """,
                    (product_id, store_id, name),
                )

            for order_id, store_id in ((order_a, store_a), (order_b, store_b)):
                cur.execute(
                    """
                    INSERT INTO public.orders (
                        id, store_id, origin, status, currency, placed_at
                    ) VALUES (%s, %s, 'cod', 'pending', 'SAR', now())
                    """,
                    (order_id, store_id),
                )

    return SeedData(
        user_a=user_a,
        user_b=user_b,
        store_a=store_a,
        store_b=store_b,
        product_a=product_a,
        product_b=product_b,
        order_a=order_a,
        order_b=order_b,
    )


def _build_app():
    app = create_app()

    @app.get("/_test/products")
    def list_products(
        tenant=Depends(get_tenant),
        session: Session = Depends(get_session),
    ):
        repository = TenantScopedRepository(session, "products")
        return [
            {
                "id": str(row["id"]),
                "store_id": str(row["store_id"]),
                "name": row["name"],
            }
            for row in repository.list()
        ]

    @app.get("/_test/products/{product_id}")
    def get_product(
        product_id: uuid.UUID,
        request: Request,
        tenant=Depends(get_tenant),
        session: Session = Depends(get_session),
    ):
        repository = TenantScopedRepository(session, "products")
        row = get_owned_or_404(
            repository,
            product_id,
            target_type="product",
            tenant=tenant,
            request=request,
        )
        return {
            "id": str(row["id"]),
            "store_id": str(row["store_id"]),
            "name": row["name"],
        }

    @app.get("/_test/orders")
    def list_orders(
        tenant=Depends(get_tenant),
        session: Session = Depends(get_session),
    ):
        repository = TenantScopedRepository(session, "orders")
        return [
            {
                "id": str(row["id"]),
                "store_id": str(row["store_id"]),
                "status": row["status"],
            }
            for row in repository.list()
        ]

    @app.get("/_test/tenant-settings")
    def tenant_settings(session: Session = Depends(get_session)):
        row = session.execute(
            text(
                "SELECT current_setting('app.store_id', true), "
                "current_setting('app.user_id', true)"
            )
        ).one()
        return {"store_id": row[0], "user_id": row[1]}

    return app


@pytest.fixture()
def app(scratch_url: str, seed: SeedData, monkeypatch):
    monkeypatch.setenv("MUSAWIQ_DATABASE_URL", scratch_url)
    get_settings.cache_clear()
    dispose_engine()
    return _build_app()


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client
    dispose_engine()
    get_settings.cache_clear()
