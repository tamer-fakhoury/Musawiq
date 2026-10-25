"""Fixtures for audit-service integration tests.

The fixture creates a disposable database owned by the application role, runs
the full migration chain as that role, and seeds two independent stores. This
keeps RLS active during the API tests and in the direct policy assertion.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
import pytest
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from musawiq.api.app import create_app
from musawiq.api.deps import get_session, get_tenant
from musawiq.config import get_settings
from musawiq.db.session import dispose_engine
from musawiq.middleware.tenant import error_envelope, get_correlation_id
from musawiq.repositories.base import TenantScopedRepository
from musawiq.services.audit import AuditService
from scripts.gen_schema_docs import libpq_url, quote_ident, with_database

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Scratch:
    url: str
    admin_url: str


@dataclass(frozen=True)
class SeedData:
    user_a: uuid.UUID
    user_b: uuid.UUID
    store_a: uuid.UUID
    store_b: uuid.UUID
    product_a: uuid.UUID
    product_b: uuid.UUID


@contextmanager
def _scratch_database():
    admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
    app_url = os.getenv("MUSAWIQ_DATABASE_URL")
    if not admin_url or not app_url:
        pytest.fail(
            "MUSAWIQ_ADMIN_DATABASE_URL and MUSAWIQ_DATABASE_URL are required"
        )

    scratch = f"musawiq_audit_service_{uuid.uuid4().hex[:10]}"
    app_user = urlsplit(app_url).username
    admin = psycopg.connect(libpq_url(admin_url), autocommit=True)
    try:
        with admin.cursor() as cur:
            owner = f" OWNER {quote_ident(app_user)}" if app_user else ""
            cur.execute(f"CREATE DATABASE {quote_ident(scratch)}{owner}")

        scratch_url = with_database(app_url, scratch)
        env = os.environ.copy()
        env["MUSAWIQ_DATABASE_URL"] = scratch_url
        process = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        if process.returncode != 0:
            pytest.fail(
                "alembic upgrade head failed for audit-service scratch database: "
                + (process.stderr or process.stdout)
            )

        yield Scratch(
            url=scratch_url,
            admin_url=with_database(admin_url, scratch),
        )
    finally:
        with admin.cursor() as cur:
            cur.execute(
                f"DROP DATABASE IF EXISTS {quote_ident(scratch)} WITH (FORCE)"
            )
        admin.close()


@pytest.fixture(scope="module")
def scratch() -> Scratch:
    with _scratch_database() as database:
        yield database


@pytest.fixture(scope="module")
def seed(scratch: Scratch) -> SeedData:
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    store_a, store_b = uuid.uuid4(), uuid.uuid4()
    product_a, product_b = uuid.uuid4(), uuid.uuid4()

    with psycopg.connect(libpq_url(scratch.admin_url), autocommit=True) as conn:
        with conn.cursor() as cur:
            for user_id, email, name in (
                (user_a, f"audit-a-{user_a.hex}@dev.local", "Audit Owner A"),
                (user_b, f"audit-b-{user_b.hex}@dev.local", "Audit Owner B"),
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
                (store_a, user_a, "Audit Store A", f"audit-a-{store_a.hex}"),
                (store_b, user_b, "Audit Store B", f"audit-b-{store_b.hex}"),
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
                (product_a, store_a, "Audit Product A"),
                (product_b, store_b, "Audit Product B"),
            ):
                cur.execute(
                    """
                    INSERT INTO public.products (
                        id, store_id, name, currency, source
                    ) VALUES (%s, %s, %s, 'SAR', 'manual')
                    """,
                    (product_id, store_id, name),
                )

    return SeedData(
        user_a=user_a,
        user_b=user_b,
        store_a=store_a,
        store_b=store_b,
        product_a=product_a,
        product_b=product_b,
    )


def _build_app():
    app = create_app()

    @app.post("/_test/audit-write")
    def audit_write(
        payload: dict,
        request: Request,
        tenant=Depends(get_tenant),
        session: Session = Depends(get_session),
    ):
        row = AuditService.from_request(request, session).record(
            action=payload["action"],
            target_type=payload["target_type"],
            target_id=payload.get("target_id"),
            before=payload.get("before"),
            after=payload.get("after"),
            metadata=payload.get("metadata"),
        )
        return {
            "id": str(row["id"]),
            "created_at": row["created_at"].isoformat(),
        }

    @app.post("/_test/products/{product_id}/rename")
    def rename_product(
        product_id: uuid.UUID,
        payload: dict,
        request: Request,
        tenant=Depends(get_tenant),
        session: Session = Depends(get_session),
    ):
        repository = TenantScopedRepository(session, "products")
        before = repository.get(product_id)
        if before is None:
            raise HTTPException(
                status_code=404,
                detail=error_envelope(
                    "not_found",
                    "Resource not found",
                    get_correlation_id(request),
                ),
            )
        updated = repository.update(product_id, {"name": payload["name"]})
        if updated is None:
            raise HTTPException(status_code=404, detail="Resource not found")
        AuditService.from_request(request, session).record(
            action="product.renamed",
            target_type="product",
            target_id=product_id,
            before={"name": before["name"]},
            after={"name": updated["name"]},
        )
        return {"id": str(updated["id"]), "name": updated["name"]}

    return app


@pytest.fixture()
def client(scratch: Scratch, seed: SeedData, monkeypatch):
    monkeypatch.setenv("MUSAWIQ_DATABASE_URL", scratch.url)
    get_settings.cache_clear()
    dispose_engine()
    app = _build_app()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        dispose_engine()
        get_settings.cache_clear()


def headers(
    store_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    role: str = "owner",
    correlation_id: uuid.UUID | None = None,
    ip_hash: str | None = None,
    raw_ip: str | None = None,
) -> dict[str, str]:
    values = {
        "X-Store-Id": str(store_id),
        "X-User-Id": str(user_id),
        "X-User-Role": role,
    }
    if correlation_id is not None:
        values["X-Correlation-Id"] = str(correlation_id)
    if ip_hash is not None:
        values["X-IP-Hash"] = ip_hash
    if raw_ip is not None:
        values["X-Forwarded-For"] = raw_ip
    return values
