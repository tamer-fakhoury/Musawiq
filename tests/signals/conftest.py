"""Fixtures for signal ingestion tests."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from musawiq.api.routers.signals import router as signals_router
from musawiq.config import get_settings
from musawiq.db.session import dispose_engine
from musawiq.middleware.tenant import (
    DevHeaderTenantProvider,
    TenantMiddleware,
)

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class CampaignTenant:
    store_id: uuid.UUID
    user_id: uuid.UUID
    campaign_id: uuid.UUID
    test_id: uuid.UUID


def _libpq_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def _with_database(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{database}"))


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@pytest.fixture(scope="session")
def migrated_db_url() -> Iterator[str]:
    admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
    if not admin_url:
        pytest.skip("MUSAWIQ_ADMIN_DATABASE_URL is not set")

    scratch = f"musawiq_signals_{uuid.uuid4().hex[:10]}"
    admin_conn_url = _libpq_url(admin_url)
    scratch_url = _with_database(admin_url, scratch)

    with psycopg.connect(admin_conn_url, autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE {_quote_ident(scratch)}")

    try:
        env = os.environ.copy()
        env["MUSAWIQ_DATABASE_URL"] = scratch_url
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "alembic upgrade failed for signals test database:\n"
                f"{result.stdout}\n{result.stderr}"
            )
        yield scratch_url
    finally:
        with psycopg.connect(admin_conn_url, autocommit=True) as conn:
            conn.execute(
                f"DROP DATABASE IF EXISTS {_quote_ident(scratch)} WITH (FORCE)"
            )


@pytest.fixture(scope="session")
def db_engine(migrated_db_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_db_url, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


def _seed_campaign(engine: Engine) -> CampaignTenant:
    store_id = uuid.uuid4()
    user_id = uuid.uuid4()
    suffix = uuid.uuid4().hex[:12]

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO users (id, email, full_name, role, status)
                VALUES (:id, :email, 'Signals Test Owner', 'owner', 'active')
                """
            ),
            {"id": user_id, "email": f"signals-{suffix}@example.com"},
        )
        conn.execute(
            text(
                """
                INSERT INTO stores (
                    id, owner_user_id, name, slug, status,
                    default_currency, default_language, timezone, country_code,
                    onboarding_status
                )
                VALUES (
                    :id, :owner_user_id, 'Signals Test Store', :slug, 'active',
                    'USD', 'en', 'UTC', 'US', 'completed'
                )
                """
            ),
            {
                "id": store_id,
                "owner_user_id": user_id,
                "slug": f"signals-{suffix}",
            },
        )
        category_id = conn.execute(
            text(
                """
                INSERT INTO categories (name, slug)
                VALUES ('Signals Category', :slug)
                RETURNING id
                """
            ),
            {"slug": f"signals-category-{suffix}"},
        ).scalar_one()
        concept_id = conn.execute(
            text(
                """
                INSERT INTO product_concepts (
                    store_id, name, category_id, price_minor, cost_minor,
                    currency, gross_margin_bp, created_by
                )
                VALUES (
                    :store_id, 'Signals Concept', :category_id, 1000, 400,
                    'USD', 6000, :user_id
                )
                RETURNING id
                """
            ),
            {
                "store_id": store_id,
                "category_id": category_id,
                "user_id": user_id,
            },
        ).scalar_one()
        test_id = conn.execute(
            text(
                """
                INSERT INTO tests (
                    store_id, product_concept_id, name, status,
                    primary_conversion, currency, total_budget_minor,
                    daily_budget_minor, planned_start_at, planned_end_at,
                    created_by
                )
                VALUES (
                    :store_id, :concept_id, 'Signals Test', 'draft',
                    'whatsapp_click', 'USD', 100000, 10000,
                    now(), now() + interval '7 days', :user_id
                )
                RETURNING id
                """
            ),
            {
                "store_id": store_id,
                "concept_id": concept_id,
                "user_id": user_id,
            },
        ).scalar_one()
        campaign_id = conn.execute(
            text(
                """
                INSERT INTO campaigns (
                    store_id, test_id, provider, name, objective, status,
                    budget_type, budget_minor, currency, start_at, end_at,
                    created_by
                )
                VALUES (
                    :store_id, :test_id, 'meta', 'Signals Campaign',
                    'conversions', 'draft', 'daily', 10000, 'USD',
                    now(), now() + interval '7 days', :user_id
                )
                RETURNING id
                """
            ),
            {
                "store_id": store_id,
                "test_id": test_id,
                "user_id": user_id,
            },
        ).scalar_one()

    return CampaignTenant(
        store_id=store_id,
        user_id=user_id,
        campaign_id=campaign_id,
        test_id=test_id,
    )


@pytest.fixture()
def campaign(db_engine: Engine) -> Iterator[CampaignTenant]:
    yield _seed_campaign(db_engine)


@pytest.fixture()
def make_campaign(db_engine: Engine) -> Iterator:
    def factory() -> CampaignTenant:
        return _seed_campaign(db_engine)

    yield factory


@pytest.fixture()
def client(migrated_db_url: str, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MUSAWIQ_DATABASE_URL", migrated_db_url)
    get_settings.cache_clear()
    dispose_engine()

    app = FastAPI()
    app.include_router(signals_router)
    app.add_middleware(TenantMiddleware, provider=DevHeaderTenantProvider())

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        dispose_engine()
        get_settings.cache_clear()
