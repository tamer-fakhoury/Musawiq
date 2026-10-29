"""Batch viability evaluation job handler."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text

from musawiq.db.session import get_session_factory
from musawiq.db.tenant import set_local_tenant
from musawiq.jobs.models import JobOutcome
from musawiq.services.evaluations import evaluate_concept


def _store_owner(session, store_id) -> Any:
    return session.execute(
        text("SELECT owner_user_id FROM stores WHERE id = :id"),
        {"id": store_id},
    ).scalar_one()


def _progress(session, job_id, *, current: int, total: int) -> None:
    session.execute(
        text(
            """
            UPDATE async_jobs
            SET progress_current = :current, progress_total = :total
            WHERE id = :id
            """
        ),
        {"id": job_id, "current": current, "total": total},
    )


def run_batch_evaluation_job(
    job: Mapping[str, Any],
) -> JobOutcome:
    payload = job.get("payload") or {}
    concept_ids = payload.get("concept_ids")
    if not isinstance(concept_ids, list) or not concept_ids:
        return JobOutcome(
            state="failed",
            error_code="invalid_payload",
            error_message="concept_ids must be a non-empty list",
        )

    session = get_session_factory()()
    try:
        session.begin()
        store_id = job["store_id"]
        requested_by = payload.get("requested_by") or _store_owner(
            session, store_id
        )
        tenant = set_local_tenant(
            session,
            store_id,
            requested_by,
            str(payload.get("requested_role") or "owner"),
        )
        model_id = payload.get("model_id")
        total = len(concept_ids)
        _progress(session, job["id"], current=0, total=total)
        session.commit()
        tenant = set_local_tenant(
            session,
            store_id,
            requested_by,
            str(payload.get("requested_role") or "owner"),
        )

        results: list[dict[str, Any]] = []
        for index, concept_id in enumerate(concept_ids, start=1):
            try:
                with session.begin_nested():
                    evaluation = evaluate_concept(
                        session,
                        tenant,
                        concept_id,
                        model_id=model_id,
                    )
                results.append(
                    {
                        "concept_id": str(concept_id),
                        "evaluation": evaluation,
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "concept_id": str(concept_id),
                        "error": type(exc).__name__,
                        "message": str(exc)[:200],
                    }
                )
            _progress(session, job["id"], current=index, total=total)
            session.commit()
            tenant = set_local_tenant(
                session,
                store_id,
                requested_by,
                str(payload.get("requested_role") or "owner"),
            )

        failed = sum(1 for result in results if "error" in result)
        return JobOutcome(
            state="succeeded" if failed == 0 else "partial",
            result={
                "results": results,
                "succeeded": len(results) - failed,
                "failed": failed,
            },
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = ["run_batch_evaluation_job"]
