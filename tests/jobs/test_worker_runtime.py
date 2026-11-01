"""Worker runtime: dispatch, retries, heartbeat, and fail-fast handlers."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from musawiq.api.app import create_app
from musawiq.config import get_settings
from musawiq.db.session import dispose_engine
from musawiq.jobs.handlers import JOB_HANDLERS
from musawiq.jobs.queue import enqueue
from scripts.worker import ensure_handlers, run_batch


def _enqueue(db_session, tenant, job_type="import", correlation_id=None):
    return enqueue(
        job_type,
        {"schema_version": 1},
        correlation_id=correlation_id or str(uuid.uuid4()),
        session=db_session,
    )


def test_worker_dispatches_queued_jobs_and_records_heartbeat(
    db_engine, db_session, tenant
):
    correlation_id = str(uuid.uuid4())
    job = _enqueue(db_session, tenant, correlation_id=correlation_id)
    db_session.commit()

    result = run_batch(db_engine, worker_name="test-worker")

    assert result["processed"] >= 1
    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT state, attempt_count, started_at, finished_at, "
                "correlation_id FROM async_jobs WHERE id = :id"
            ),
            {"id": job["id"]},
        ).mappings().one()
        heartbeat = conn.execute(
            text(
                "SELECT status, processed_jobs, failed_jobs, last_heartbeat_at "
                "FROM worker_heartbeats WHERE worker_name = 'test-worker'"
            )
        ).mappings().one()
    assert row["state"] == "succeeded"
    assert row["attempt_count"] == 1
    assert row["started_at"] is not None
    assert row["finished_at"] is not None
    assert str(row["correlation_id"]) == correlation_id
    assert heartbeat["status"] == "stopped"
    assert heartbeat["processed_jobs"] >= 1
    assert heartbeat["last_heartbeat_at"] is not None


def test_worker_retries_failed_jobs_until_max_attempts(
    db_engine, db_session, tenant, monkeypatch
):
    def failing(job):
        raise RuntimeError("boom")

    monkeypatch.setitem(JOB_HANDLERS, "import", failing)
    job = _enqueue(db_session, tenant)
    db_session.commit()

    run_batch(db_engine, worker_name="retry-worker")

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT state, attempt_count, error_code, error_message "
                "FROM async_jobs WHERE id = :id"
            ),
            {"id": job["id"]},
        ).mappings().one()
    assert row["state"] == "failed"
    assert row["attempt_count"] == 3
    assert row["error_code"] == "handler_error"
    assert row["error_message"] == "boom"


def test_worker_fails_fast_when_a_handler_is_missing(monkeypatch):
    monkeypatch.delitem(JOB_HANDLERS, "import")
    with pytest.raises(RuntimeError, match="missing handlers"):
        ensure_handlers()


def test_worker_heartbeat_endpoint(
    migrated_db_url, monkeypatch, db_engine, db_session, tenant
):
    job = _enqueue(db_session, tenant)
    db_session.commit()
    run_batch(db_engine, worker_name="endpoint-worker")

    monkeypatch.setenv("MUSAWIQ_DATABASE_URL", migrated_db_url)
    get_settings.cache_clear()
    dispose_engine()
    try:
        with TestClient(create_app()) as client:
            response = client.get("/health/workers")
    finally:
        dispose_engine()
        get_settings.cache_clear()

    assert response.status_code == 200
    names = {row["worker_name"] for row in response.json()["workers"]}
    assert "endpoint-worker" in names


def test_handler_registry_covers_every_valid_job_type():
    ensure_handlers()


def test_worker_generation_handler_is_reachable(db_engine, db_session, tenant):
    assert "page_generation" in JOB_HANDLERS
    assert JOB_HANDLERS["page_generation"] is not None
