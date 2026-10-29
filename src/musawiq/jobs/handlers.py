"""Job handler registry and the first no-op handler."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from musawiq.jobs.models import JobOutcome
from musawiq.services.page_generation import run_page_generation_job
from musawiq.workers.batch_evaluation import run_batch_evaluation_job

JobHandler = Callable[[Mapping[str, Any]], JobOutcome | Mapping[str, Any] | Any]


def noop(job: Mapping[str, Any]) -> JobOutcome:
    """Do nothing and report success."""
    return JobOutcome(result={"ok": True})


JOB_HANDLERS: dict[str, JobHandler] = {
    "import": noop,
    "batch_evaluation": run_batch_evaluation_job,
    "page_generation": run_page_generation_job,
}


def register_handler(job_type: str, handler: JobHandler) -> None:
    JOB_HANDLERS[job_type] = handler


def unregister_handler(job_type: str) -> None:
    JOB_HANDLERS.pop(job_type, None)


__all__ = [
    "JOB_HANDLERS",
    "JobHandler",
    "noop",
    "register_handler",
    "unregister_handler",
]
