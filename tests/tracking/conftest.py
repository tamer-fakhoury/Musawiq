"""Fixtures for first-party visitor tracking (FR-4.1.2) tests."""

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
class Site:
    store_id: uuid.UUID
    user_id: uuid.UUID
    page_slug: str
    draft_slug: str


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

    scratch = f"musawiq_tracking_{uuid.uuid4().hex[:10]}"
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
            "alembic upgrade failed for tracking test database:\n"
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


def _seed_site(engine: Engine) -> Site:
    site = Site(
        store_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        page_slug=f"landing-{uuid.uuid4().hex[:8]}",
        draft_slug=f"draft-{uuid.uuid4().hex[:8]}",
    )
    category_id = uuid.uuid4()
    concept_id = uuid.uuid4()
    suffix = uuid.uuid4().hex[:12]
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO users (id, email, full_name, role, status)
                VALUES (:id, :email, 'Tracking Owner', 'owner', 'active')
                """
            ),
            {"id": site.user_id, "email": f"tracking-{suffix}@example.com"},
        )
        conn.execute(
            text(
                """
                INSERT INTO stores (
                    id, owner_user_id, name, slug, status,
                    default_currency, default_language, timezone, country_code,
                    onboarding_status
                ) VALUES (
                    :id, :owner_user_id, 'Tracking Store', :slug, 'active',
                    'USD', 'en', 'UTC', 'US', 'completed'
                )
                """
            ),
            {
                "id": site.store_id,
                "owner_user_id": site.user_id,
                "slug": f"tracking-{suffix}",
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO categories (id, name, slug, is_active, sort_order)
                VALUES (:id, 'Home', :slug, true, 10)
                """
            ),
            {"id": category_id, "slug": f"home-{suffix}"},
        )
        conn.execute(
            text(
                """
                INSERT INTO product_concepts (
                    id, store_id, name, category_id, price_minor, cost_minor,
                    currency, gross_margin_bp, created_by
                ) VALUES (
                    :id, :store_id, 'Tracked Concept', :category_id, 5000,
                    2000, 'USD', 6000, :created_by
                )
                """
            ),
            {
                "id": concept_id,
                "store_id": site.store_id,
                "category_id": category_id,
                "created_by": site.user_id,
            },
        )
        template_id = conn.execute(
            text(
                """
                INSERT INTO page_templates (key, version, name, schema)
                VALUES (:key, 1, 'Tracking', '{"schema_version": 1}'::jsonb)
                RETURNING id
                """
            ),
            {"key": f"tracking-{suffix}"},
        ).scalar_one()
        for slug, status in (
            (site.page_slug, "published"),
            (site.draft_slug, "draft"),
        ):
            conn.execute(
                text(
                    """
                    INSERT INTO landing_pages (
                        store_id, product_concept_id, slug, status, template_id,
                        language, currency, published_url
                    ) VALUES (
                        :store_id, :concept_id, :slug, :status, :template_id,
                        'en', 'USD', :url
                    )
                    """
                ),
                {
                    "store_id": site.store_id,
                    "concept_id": concept_id,
                    "slug": slug,
                    "status": status,
                    "template_id": template_id,
                    "url": (
                        f"https://pages.musawiq.app/p/{slug}"
                        if status == "published"
                        else None
                    ),
                },
            )
    return site


@pytest.fixture()
def site(db_engine: Engine) -> Iterator[Site]:
    yield _seed_site(db_engine)


@pytest.fixture()
def client(migrated_db_url: str, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MUSAWIQ_DATABASE_URL", migrated_db_url)
    get_settings.cache_clear()
    dispose_engine()
    app = create_app()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        dispose_engine()
        get_settings.cache_clear()
