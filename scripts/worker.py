"""Background job worker runtime.

Usage:
    .venv\\Scripts\\python.exe -m scripts.worker           # run forever
    .venv\\Scripts\\python.exe -m scripts.worker --once    # drain then exit
    .venv\\Scripts\\python.exe -m scripts.worker --interval 5
"""

from __future__ import annotations

import argparse
import logging
import signal
import time
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from musawiq.config import get_settings
from musawiq.db.session import get_engine
from musawiq.db.tenant import set_local_tenant
from musawiq.jobs.handlers import JOB_HANDLERS
from musawiq.jobs.queue import VALID_JOB_TYPES
from musawiq.jobs.worker import claim_next, claim_next_system, run_job

logger = logging.getLogger("musawiq.worker")
HEARTBEAT_TABLE = "worker_heartbeats"


def ensure_handlers() -> None:
    """Fail fast when a valid job type has no registered handler."""
    missing = sorted(VALID_JOB_TYPES - set(JOB_HANDLERS))
    if missing:
        raise RuntimeError(
            "Worker cannot start; missing handlers for: " + ", ".join(missing)
        )


def _heartbeat(
    session: Session,
    worker_name: str,
    *,
    status: str,
    processed: int,
    failed: int,
    started: bool = False,
) -> None:
    if started:
        session.execute(
            text(
                """
                INSERT INTO worker_heartbeats (
                    worker_name, status, processed_jobs, failed_jobs,
                    started_at, last_heartbeat_at
                ) VALUES (:name, :status, :processed, :failed, now(), now())
                ON CONFLICT (worker_name) DO UPDATE SET
                    status = EXCLUDED.status,
                    processed_jobs = EXCLUDED.processed_jobs,
                    failed_jobs = EXCLUDED.failed_jobs,
                    last_heartbeat_at = now()
                """
            ),
            {
                "name": worker_name,
                "status": status,
                "processed": processed,
                "failed": failed,
            },
        )
        return
    session.execute(
        text(
            """
            INSERT INTO worker_heartbeats (
                worker_name, status, processed_jobs, failed_jobs
            ) VALUES (:name, :status, :processed, :failed)
            ON CONFLICT (worker_name) DO UPDATE SET
                status = EXCLUDED.status,
                processed_jobs = EXCLUDED.processed_jobs,
                failed_jobs = EXCLUDED.failed_jobs,
                last_heartbeat_at = now()
            """
        ),
        {
            "name": worker_name,
            "status": status,
            "processed": processed,
            "failed": failed,
        },
    )


def _requeue_if_retryable(session: Session, job: dict[str, Any]) -> bool:
    if job["state"] != "failed":
        return False
    if int(job["attempt_count"]) >= int(job["max_attempts"]):
        return False
    session.execute(
        text(
            """
            UPDATE async_jobs
            SET state = 'queued', started_at = NULL, finished_at = NULL
            WHERE id = :id AND store_id IS NOT DISTINCT FROM :store_id
            """
        ),
        {"id": job["id"], "store_id": job.get("store_id")},
    )
    return True


def _claim_and_run(
    session: Session, *, system: bool, tenant: Any = None
) -> dict[str, Any] | None:
    if session.in_transaction():
        session.rollback()
    session.begin()
    if tenant is not None:
        set_local_tenant(
            session, tenant["id"], tenant["owner_user_id"], "owner"
        )
    if system:
        job = claim_next_system(session)
    else:
        job = claim_next(session)
    if job is None:
        session.rollback()
        return None
    job = dict(job)
    finished = dict(run_job(session, job))
    session.commit()
    requeued = False
    if finished["state"] == "failed":
        session.begin()
        requeued = _requeue_if_retryable(session, finished)
        session.commit()
    logger.info(
        "job_finished",
        extra={
            "job_id": str(finished["id"]),
            "job_type": finished["job_type"],
            "state": finished["state"],
            "attempt": finished["attempt_count"],
            "correlation_id": str(finished.get("correlation_id") or ""),
            "requeued": requeued,
        },
    )
    return {**finished, "requeued": requeued}


def run_batch(
    engine: Engine,
    *,
    worker_name: str = "worker",
    max_jobs: int | None = None,
) -> dict[str, int]:
    """Drain currently queued jobs for all active stores once."""
    ensure_handlers()
    processed = 0
    failed = 0
    requeued = 0
    session = Session(bind=engine)
    try:
        with session.begin():
            _heartbeat(
                session,
                worker_name,
                status="running",
                processed=0,
                failed=0,
                started=True,
            )
        while max_jobs is None or processed < max_jobs:
            result = _claim_and_run(session, system=True)
            if result is not None:
                processed += 1
                failed += int(result["state"] == "failed")
                requeued += int(result["requeued"])
                if max_jobs is not None and processed >= max_jobs:
                    break
                continue

            stores = session.execute(
                text(
                    "SELECT id, owner_user_id FROM stores "
                    "WHERE status = 'active' AND deleted_at IS NULL "
                    "ORDER BY created_at, id"
                )
            ).mappings().all()
            claimed = False
            for store in stores:
                result = _claim_and_run(
                    session, system=False, tenant=store
                )
                if result is not None:
                    claimed = True
                    processed += 1
                    failed += int(result["state"] == "failed")
                    requeued += int(result["requeued"])
                    if max_jobs is not None and processed >= max_jobs:
                        break
            if not claimed:
                break
    finally:
        session.close()
    with Session(bind=engine) as heartbeat_session:
        with heartbeat_session.begin():
            _heartbeat(
                heartbeat_session,
                worker_name,
                status="stopped",
                processed=processed,
                failed=failed,
            )
    return {
        "processed": processed,
        "failed": failed,
        "requeued": requeued,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Musawiq background job worker")
    parser.add_argument("--once", action="store_true", help="drain then exit")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument(
        "--worker-name",
        default=f"worker-{uuid.uuid4().hex[:8]}",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, get_settings().log_level, logging.INFO)
    )
    ensure_handlers()
    engine = get_engine()

    stopping = False

    def _stop(signum, frame):  # noqa: ANN001
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    logger.info("worker_started", extra={"worker": args.worker_name})
    while not stopping:
        result = run_batch(engine, worker_name=args.worker_name)
        logger.info("worker_pass", extra=result)
        if args.once:
            break
        if result["processed"] == 0:
            time.sleep(args.interval)
    logger.info("worker_stopped", extra={"worker": args.worker_name})


if __name__ == "__main__":
    main()
