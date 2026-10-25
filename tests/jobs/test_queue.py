"""Queue and worker unit contracts."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from musawiq.jobs.handlers import JOB_HANDLERS
from musawiq.jobs.models import JobOutcome
from musawiq.jobs.queue import enqueue
from musawiq.jobs.worker import claim_next, run_job


def test_enqueue_is_idempotent(db_session) -> None:
    first = enqueue(
        "import",
        {"n": 1},
        idempotency_key="same-key",
        correlation_id=str(uuid.uuid4()),
        session=db_session,
    )
    second = enqueue(
        "import",
        {"n": 2},
        idempotency_key="same-key",
        session=db_session,
    )

    assert first["id"] == second["id"]
    assert first["payload"]["n"] == 1
    count = db_session.execute(
        text(
            "SELECT count(*) FROM async_jobs "
            "WHERE idempotency_key = 'same-key'"
        )
    ).scalar_one()
    assert count == 1


def test_claim_next_returns_a_job_once(db_session) -> None:
    enqueue("import", {}, session=db_session)

    first = claim_next(db_session)
    assert first is not None
    assert first["state"] == "running"
    assert first["attempt_count"] == 1
    assert first["started_at"] is not None

    assert claim_next(db_session) is None


def test_run_job_supports_partial(db_session, monkeypatch) -> None:
    def partial_handler(job):
        return JobOutcome(state="partial", result={"processed": 1})

    monkeypatch.setitem(JOB_HANDLERS, "import", partial_handler)
    enqueue("import", {}, session=db_session)
    job = claim_next(db_session)
    assert job is not None

    finished = run_job(db_session, job)

    assert finished["state"] == "partial"
    assert finished["result"] == {"processed": 1}
    assert finished["finished_at"] is not None


def test_run_job_failure_is_persisted(db_session, monkeypatch) -> None:
    def raising_handler(job):
        raise RuntimeError("boom")

    monkeypatch.setitem(JOB_HANDLERS, "import", raising_handler)
    enqueue("import", {}, session=db_session)
    job = claim_next(db_session)
    assert job is not None

    finished = run_job(db_session, job)

    assert finished["state"] == "failed"
    assert finished["error_code"] == "handler_error"
    assert finished["error_message"] == "boom"
    assert finished["finished_at"] is not None
