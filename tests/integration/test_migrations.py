"""Migration path regression: 0020 batch evaluation -> 0021 public pages."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _libpq(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def _scratch_url(url: str, name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{name}"))


def _alembic(url: str, revision: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["MUSAWIQ_DATABASE_URL"] = url
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_existing_0020_database_upgrades_to_public_page_head() -> None:
    admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
    if not admin_url:
        pytest.skip("MUSAWIQ_ADMIN_DATABASE_URL is not set")

    name = f"musawiq_migration_{uuid.uuid4().hex[:10]}"
    admin = _libpq(admin_url)
    scratch = _scratch_url(admin_url, name)
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    try:
        first = _alembic(scratch, "0020")
        assert first.returncode == 0, first.stderr
        second = _alembic(scratch, "head")
        assert second.returncode == 0, second.stderr

        with psycopg.connect(_libpq(scratch)) as conn:
            revision = conn.execute(
                "SELECT version_num FROM schema_migrations"
            ).fetchone()[0]
            check = conn.execute(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname = 'ck_async_jobs_job_type'
                """
            ).fetchone()[0]
            policies = {
                row[0]
                for row in conn.execute(
                    """
                    SELECT policyname FROM pg_policies
                    WHERE policyname IN (
                        'p_landing_pages_public_read',
                        'p_page_versions_public_read'
                    )
                    """
                ).fetchall()
            }
        assert revision == "0021"
        assert "batch_evaluation" in check
        assert policies == {
            "p_landing_pages_public_read",
            "p_page_versions_public_read",
        }
    finally:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
