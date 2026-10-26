"""Fixtures for import preview endpoint tests."""

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

from musawiq.api.app import create_app
from musawiq.api.routers.import_preview import router as import_preview_router
from musawiq.config import get_settings
from musawiq.db.session import dispose_engine

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Seed:
    store_id: uuid.UUID
    other_store_id: uuid.UUID
    user_id: uuid.UUID
    other_user_id: uuid.UUID
    preview_batch: uuid.UUID
    not_validated_batch: uuid.UUID
    csv_batch: uuid.UUID
    empty_batch: uuid.UUID
    other_batch: uuid.UUID


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

    scratch = f"musawiq_preview_{uuid.uuid4().hex[:10]}"
    scratch_url = _with_database(admin_url, scratch)
    with psycopg.connect(_libpq_url(admin_url), autocommit=True) as conn:
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
            pytest.fail("alembic upgrade failed: " + result.stderr)
        yield scratch_url
    finally:
        with psycopg.connect(_libpq_url(admin_url), autocommit=True) as conn:
            conn.execute(
                f"DROP DATABASE IF EXISTS {_quote_ident(scratch)} WITH (FORCE)"
            )


def _seed(url: str) -> Seed:
    store_id, other_store_id = uuid.uuid4(), uuid.uuid4()
    user_id, other_user_id = uuid.uuid4(), uuid.uuid4()
    preview_batch, not_validated_batch = uuid.uuid4(), uuid.uuid4()
    csv_batch, empty_batch, other_batch = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            for tenant_user, email in (
                (user_id, f"preview-{user_id.hex}@dev.local"),
                (other_user_id, f"preview-{other_user_id.hex}@dev.local"),
            ):
                conn.execute(
                    text(
                        """
                        INSERT INTO users (id, email, full_name, role, status)
                        VALUES (:id, :email, 'Preview Owner', 'owner', 'active')
                        """
                    ),
                    {"id": tenant_user, "email": email},
                )

            for tenant_store, owner, name in (
                (store_id, user_id, "Preview Store"),
                (other_store_id, other_user_id, "Other Preview Store"),
            ):
                conn.execute(
                    text(
                        """
                        INSERT INTO stores (
                            id, owner_user_id, name, slug, status,
                            default_currency, default_language, timezone,
                            country_code, onboarding_status
                        ) VALUES (
                            :id, :owner, :name, :slug, 'active',
                            'USD', 'en', 'UTC', 'US', 'completed'
                        )
                        """
                    ),
                    {
                        "id": tenant_store,
                        "owner": owner,
                        "name": name,
                        "slug": f"preview-{tenant_store.hex}",
                    },
                )

            def stored_file(store: uuid.UUID, user: uuid.UUID) -> uuid.UUID:
                file_id = uuid.uuid4()
                conn.execute(
                    text(
                        """
                        INSERT INTO stored_files (
                            id, store_id, purpose, original_filename, mime_type,
                            size_bytes, checksum_sha256, storage_provider,
                            storage_key, status, uploaded_by_user_id
                        ) VALUES (
                            :id, :store, 'sales_csv', 'sales.csv', 'text/csv',
                            0, repeat('0', 64), 'local', :key, 'committed', :user
                        )
                        """
                    ),
                    {
                        "id": file_id,
                        "store": store,
                        "key": f"preview-{file_id}",
                        "user": user,
                    },
                )
                return file_id

            def batch(
                batch_id: uuid.UUID,
                store: uuid.UUID,
                user: uuid.UUID,
                *,
                status: str,
                total: int = 0,
                valid: int = 0,
                invalid: int = 0,
                duplicate: int = 0,
            ) -> None:
                conn.execute(
                    text(
                        """
                        INSERT INTO import_batches (
                            id, store_id, source_type, stored_file_id, status,
                            total_rows, valid_rows, invalid_rows,
                            duplicate_rows, created_by
                        ) VALUES (
                            :id, :store, 'csv', :file, :status,
                            :total, :valid, :invalid, :duplicate, :user
                        )
                        """
                    ),
                    {
                        "id": batch_id,
                        "store": store,
                        "file": stored_file(store, user),
                        "status": status,
                        "total": total,
                        "valid": valid,
                        "invalid": invalid,
                        "duplicate": duplicate,
                        "user": user,
                    },
                )

            batch(
                preview_batch,
                store_id,
                user_id,
                status="preview",
                total=4,
                valid=2,
                invalid=1,
                duplicate=1,
            )
            batch(
                not_validated_batch,
                store_id,
                user_id,
                status="uploaded",
            )
            batch(
                csv_batch,
                store_id,
                user_id,
                status="preview",
                total=1,
                invalid=1,
            )
            batch(empty_batch, store_id, user_id, status="preview")
            batch(
                other_batch,
                other_store_id,
                other_user_id,
                status="preview",
            )

            for row_number, row_status in (
                (1, "valid"),
                (2, "valid"),
                (3, "invalid"),
                (4, "duplicate"),
            ):
                conn.execute(
                    text(
                        """
                        INSERT INTO import_rows (
                            store_id, import_batch_id, row_number, raw_data,
                            status
                        ) VALUES (
                            :store, :batch, :row, '{}'::jsonb, :status
                        )
                        """
                    ),
                    {
                        "store": store_id,
                        "batch": preview_batch,
                        "row": row_number,
                        "status": row_status,
                    },
                )

            for row_number, field, code, message, raw in (
                (3, "product_id", "required", "is required", ""),
                (3, "quantity", "invalid_quantity", "must be positive", "0"),
                (3, "sales_amount", "invalid_amount", "must be non-negative", "-1"),
            ):
                conn.execute(
                    text(
                        """
                        INSERT INTO import_issues (
                            store_id, import_batch_id, row_number, field_name,
                            issue_code, severity, message, raw_value
                        ) VALUES (
                            :store, :batch, :row, :field, :code, 'error',
                            :message, :raw
                        )
                        """
                    ),
                    {
                        "store": store_id,
                        "batch": preview_batch,
                        "row": row_number,
                        "field": field,
                        "code": code,
                        "message": message,
                        "raw": raw,
                    },
                )

            conn.execute(
                text(
                    """
                    INSERT INTO import_issues (
                        store_id, import_batch_id, row_number, field_name,
                        issue_code, severity, message, raw_value
                    ) VALUES (
                        :store, :batch, 7, 'sales_amount', 'invalid_amount',
                        'error', 'must be non-negative, decimal', '-1'
                    )
                    """
                ),
                {"store": store_id, "batch": csv_batch},
            )
    finally:
        engine.dispose()

    return Seed(
        store_id=store_id,
        other_store_id=other_store_id,
        user_id=user_id,
        other_user_id=other_user_id,
        preview_batch=preview_batch,
        not_validated_batch=not_validated_batch,
        csv_batch=csv_batch,
        empty_batch=empty_batch,
        other_batch=other_batch,
    )


@pytest.fixture(scope="session")
def seed(migrated_db_url: str) -> Seed:
    return _seed(migrated_db_url)


@pytest.fixture()
def client(migrated_db_url: str, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MUSAWIQ_DATABASE_URL", migrated_db_url)
    get_settings.cache_clear()
    dispose_engine()
    app = create_app()
    app.include_router(import_preview_router)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        dispose_engine()
        get_settings.cache_clear()


def headers(seed: Seed) -> dict[str, str]:
    return {
        "X-Store-Id": str(seed.store_id),
        "X-User-Id": str(seed.user_id),
        "X-User-Role": "owner",
    }
