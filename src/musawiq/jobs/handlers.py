"""Job handler registry and the first no-op handler."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from musawiq.jobs.models import JobOutcome
from musawiq.services.page_generation import run_page_generation_job
from musawiq.workers.batch_evaluation import run_batch_evaluation_job
from musawiq.workers.recommendation_generation import (
    run_recommendation_generation_job,
)

JobHandler = Callable[[Mapping[str, Any]], JobOutcome | Mapping[str, Any] | Any]


def noop(job: Mapping[str, Any]) -> JobOutcome:
    """Do nothing and report success."""
    return JobOutcome(result={"ok": True})


def not_implemented(job_type: str) -> JobHandler:
    """Return a handler that fails visibly instead of silently queueing."""

    def handler(job: Mapping[str, Any]) -> JobOutcome:
        return JobOutcome(
            state="failed",
            error_code="handler_not_implemented",
            error_message=f"No handler is registered for {job_type!r}.",
        )

    return handler


JOB_HANDLERS: dict[str, JobHandler] = {
    "import": noop,
    "batch_evaluation": run_batch_evaluation_job,
    "page_generation": run_page_generation_job,
    "email_verification": noop,
    "recommendation_generation": run_recommendation_generation_job,
    "integration_sync": not_implemented("integration_sync"),
    "ad_publication": not_implemented("ad_publication"),
    "metric_sync": not_implemented("metric_sync"),
    "content_generation": not_implemented("content_generation"),
}


def register_handler(job_type: str, handler: JobHandler) -> None:
    JOB_HANDLERS[job_type] = handler


def unregister_handler(job_type: str) -> None:
    JOB_HANDLERS.pop(job_type, None)


__all__ = [
    "JOB_HANDLERS",
    "JobHandler",
    "noop",
    "not_implemented",
    "register_handler",
    "unregister_handler",
]
