"""Async job queue, worker, and handler registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JobOutcome:
    """Terminal result a job handler may return.

    ``state`` is normally ``succeeded`` or ``partial``. A handler can return a
    ``failed`` outcome with an explicit human-readable error instead of raising.
    """

    state: str = "succeeded"
    result: Any = None
    error_code: str | None = None
    error_message: str | None = None


__all__ = ["JobOutcome"]
