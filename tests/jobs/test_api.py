"""Job API and worker lifecycle contracts."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from musawiq.jobs.handlers import JOB_HANDLERS
from musawiq.jobs.worker import claim_next, run_job


def _headers(tenant, role: str = "owner", correlation_id: str | None = None):
    headers = {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": role,
    }
    if correlation_id is not None:
        headers["X-Correlation-ID"] = correlation_id
    return headers


def test_post_requires_write_permission(api_client, tenant) -> None:
    response = api_client.post(
        "/jobs/import",
        json={},
        headers=_headers(tenant, role="analyst"),
    )

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "permission_denied"
    assert error["correlation_id"] == response.headers["X-Correlation-ID"]


def test_enqueue_idempotent_via_api(api_client, tenant, db_session) -> None:
    correlation_id = str(uuid.uuid4())
    headers = {
        **_headers(tenant, correlation_id=correlation_id),
        "Idempotency-Key": "api-same-key",
    }

    first = api_client.post("/jobs/import", json={"n": 1}, headers=headers)
    second = api_client.post("/jobs/import", json={"n": 2}, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["state"] == "queued"
    assert first.json()["correlation_id"] == correlation_id

    count = db_session.execute(
        text(
            "SELECT count(*) FROM async_jobs "
            "WHERE idempotency_key = 'api-same-key'"
        )
    ).scalar_one()
    assert count == 1


def test_failed_job_is_exposed_by_status_endpoint(
    api_client, tenant, db_session, monkeypatch
) -> None:
    def raising_handler(job):
        raise RuntimeError("boom")

    monkeypatch.setitem(JOB_HANDLERS, "import", raising_handler)
    correlation_id = str(uuid.uuid4())
    headers = {
        **_headers(tenant, correlation_id=correlation_id),
        "Idempotency-Key": "failed-key",
    }

    created = api_client.post("/jobs/import", json={}, headers=headers)
    assert created.status_code == 202
    job_id = created.json()["id"]

    job = claim_next(db_session)
    assert job is not None
    finished = run_job(db_session, job)
    assert finished["state"] == "failed"
    db_session.commit()

    response = api_client.get(f"/jobs/{job_id}", headers=_headers(tenant))
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "failed"
    assert body["attempts"] == 1
    assert body["last_updated"] is not None
    assert body["error"]["code"] == "handler_error"
    assert body["error"]["message"] == "boom"
    assert body["error"]["correlation_id"] == correlation_id


def test_retry_failed_job_returns_to_queued(
    api_client, tenant, db_session, monkeypatch
) -> None:
    def raising_handler(job):
        raise RuntimeError("boom")

    monkeypatch.setitem(JOB_HANDLERS, "import", raising_handler)
    headers = {
        **_headers(tenant),
        "Idempotency-Key": "retry-key",
    }

    created = api_client.post("/jobs/import", json={}, headers=headers)
    job_id = created.json()["id"]
    job = claim_next(db_session)
    assert job is not None
    run_job(db_session, job)
    db_session.commit()

    retried = api_client.post(
        f"/jobs/{job_id}/retry", headers=_headers(tenant)
    )

    assert retried.status_code == 202
    assert retried.json()["id"] == job_id
    assert retried.json()["state"] == "queued"

    status_response = api_client.get(f"/jobs/{job_id}", headers=_headers(tenant))
    body = status_response.json()
    assert body["state"] == "queued"
    assert body["error"] is None

    stored = db_session.execute(
        text("SELECT idempotency_key FROM async_jobs WHERE id = :id"),
        {"id": uuid.UUID(job_id)},
    ).mappings().one()
    assert stored["idempotency_key"] == "retry-key"


def test_retry_succeeded_job_returns_409(
    api_client, tenant, db_session
) -> None:
    headers = {
        **_headers(tenant),
        "Idempotency-Key": "succeeded-key",
    }

    created = api_client.post("/jobs/import", json={}, headers=headers)
    job_id = created.json()["id"]
    job = claim_next(db_session)
    assert job is not None
    run_job(db_session, job)
    db_session.commit()

    response = api_client.post(
        f"/jobs/{job_id}/retry", headers=_headers(tenant)
    )

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "conflict"
    assert error["correlation_id"] == response.headers["X-Correlation-ID"]


def test_second_store_cannot_read_job(api_client, tenant, make_tenant) -> None:
    other = make_tenant()
    created = api_client.post(
        "/jobs/import",
        json={},
        headers=_headers(tenant),
    )
    job_id = created.json()["id"]

    response = api_client.get(f"/jobs/{job_id}", headers=_headers(other))

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["correlation_id"] == response.headers["X-Correlation-ID"]
