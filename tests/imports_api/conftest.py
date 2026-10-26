"""Fixtures for the import upload API tests."""

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
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from musawiq.api.app import create_app
from musawiq.config import get_settings
from musawiq.db.session import dispose_engine

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Tenant:
    store_id: uuid.UUID
    user_id: uuid.UUID


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

    scratch = f"musawiq_imports_{uuid.uuid4().hex[:10]}"
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
                "alembic upgrade failed for imports test database:\n"
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


def _seed_tenant(engine: Engine) -> Tenant:
    tenant = Tenant(store_id=uuid.uuid4(), user_id=uuid.uuid4())
    suffix = uuid.uuid4().hex[:12]
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO users (id, email, full_name, role, status)
                VALUES (:id, :email, 'Imports Test Owner', 'owner', 'active')
                """
            ),
            {"id": tenant.user_id, "email": f"imports-{suffix}@example.com"},
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
                    :id, :owner_user_id, 'Imports Test Store', :slug, 'active',
                    'USD', 'en', 'UTC', 'US', 'completed'
                )
                """
            ),
            {
                "id": tenant.store_id,
                "owner_user_id": tenant.user_id,
                "slug": f"imports-{suffix}",
            },
        )
    return tenant


@pytest.fixture()
def tenant(db_engine: Engine) -> Iterator[Tenant]:
    yield _seed_tenant(db_engine)


@pytest.fixture()
def make_tenant(db_engine: Engine) -> Iterator:
    def factory() -> Tenant:
        return _seed_tenant(db_engine)

    yield factory


@pytest.fixture()
def client(migrated_db_url: str, tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MUSAWIQ_DATABASE_URL", migrated_db_url)
    monkeypatch.setenv("MUSAWIQ_STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    dispose_engine()

    app = create_app()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        dispose_engine()
        get_settings.cache_clear()
