"""Fixtures for cookie session / CSRF tests (FR-0.6.4)."""

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
from musawiq.auth.signup import hash_password
from musawiq.config import get_settings
from musawiq.db.session import dispose_engine

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

PASSWORD = "correct horse battery"


@dataclass(frozen=True)
class Account:
    user_id: uuid.UUID
    store_id: uuid.UUID
    email: str


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
    scratch = f"musawiq_session_{uuid.uuid4().hex[:10]}"
    admin_conn_url = _libpq_url(admin_url)
    scratch_url = _with_database(admin_url, scratch)
    with psycopg.connect(admin_conn_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {_quote_ident(scratch)}")
        conn.execute(f"CREATE DATABASE {_quote_ident(scratch)}")
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
            "alembic upgrade failed for session test database:\n"
            f"{result.stdout}\n{result.stderr}"
        )
    try:
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


def _seed_account(engine: Engine) -> Account:
    account = Account(
        user_id=uuid.uuid4(),
        store_id=uuid.uuid4(),
        email=f"session-{uuid.uuid4().hex[:8]}@example.com",
    )
    suffix = uuid.uuid4().hex[:12]
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO users (
                    id, email, password_hash, full_name, role, status,
                    email_verified_at, auth_provider
                ) VALUES (
                    :id, :email, :hash, 'Session User', 'owner', 'active',
                    now(), 'password'
                )
                """
            ),
            {
                "id": account.user_id,
                "email": account.email,
                "hash": hash_password(PASSWORD),
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO stores (
                    id, owner_user_id, name, slug, status,
                    default_currency, default_language, timezone, country_code,
                    onboarding_status
                ) VALUES (
                    :id, :owner, 'Session Store', :slug, 'active',
                    'USD', 'en', 'UTC', 'US', 'completed'
                )
                """
            ),
            {
                "id": account.store_id,
                "owner": account.user_id,
                "slug": f"session-{suffix}",
            },
        )
    return account


@pytest.fixture()
def account(db_engine: Engine) -> Iterator[Account]:
    yield _seed_account(db_engine)


@pytest.fixture()
def client(migrated_db_url: str, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MUSAWIQ_DATABASE_URL", migrated_db_url)
    get_settings.cache_clear()
    dispose_engine()
    app = create_app()
    try:
        with TestClient(app, base_url="https://testserver") as test_client:
            yield test_client
    finally:
        dispose_engine()
        get_settings.cache_clear()
