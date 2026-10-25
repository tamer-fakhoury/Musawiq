"""Database-backed async job queue with idempotent enqueue."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import get_tenant
from musawiq.middleware.correlation import uuid7

VALID_JOB_TYPES = frozenset(
    {
        "import",
        "integration_sync",
        "page_generation",
        "ad_publication",
        "metric_sync",
        "recommendation_generation",
        "content_generation",
    }
)


class QueueError(RuntimeError):
    """Base class for queue contract violations."""


class InvalidJobType(QueueError):
    """Raised when a job type is not in the database contract."""


class IdempotencyConflict(QueueError):
    """Raised when an idempotency key is already used by another store."""


def _correlation_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return uuid7()


def enqueue(
    job_type: str,
    payload: Mapping[str, Any] | None = None,
    idempotency_key: str | None = None,
    correlation_id: str | uuid.UUID | None = None,
    *,
    session: Session,
) -> Mapping[str, Any]:
    """Insert a queued job or return the existing row for an idempotency key."""
    if job_type not in VALID_JOB_TYPES:
        raise InvalidJobType(f"unknown job type: {job_type}")

    tenant = get_tenant(session)
    key = idempotency_key.strip() if idempotency_key else None
    payload_json = json.dumps(payload if payload is not None else {})
    correlation_uuid = _correlation_uuid(correlation_id)

    params = {
        "store_id": tenant.store_id,
        "job_type": job_type,
        "payload": payload_json,
        "correlation_id": correlation_uuid,
        "idempotency_key": key,
    }

    if key is None:
        row = session.execute(
            text(
                """
                INSERT INTO async_jobs (
                    store_id, job_type, state, payload, correlation_id,
                    attempt_count, max_attempts
                )
                VALUES (
                    :store_id, :job_type, 'queued', CAST(:payload AS jsonb),
                    :correlation_id, 0, 3
                )
                RETURNING *
                """
            ),
            params,
        ).mappings().one()
        return row

    row = session.execute(
        text(
            """
            INSERT INTO async_jobs (
                store_id, job_type, state, idempotency_key, payload,
                correlation_id, attempt_count, max_attempts
            )
            VALUES (
                :store_id, :job_type, 'queued', :idempotency_key,
                CAST(:payload AS jsonb), :correlation_id, 0, 3
            )
            ON CONFLICT (idempotency_key)
                WHERE idempotency_key IS NOT NULL
                DO NOTHING
            RETURNING *
            """
        ),
        params,
    ).mappings().one_or_none()

    if row is not None:
        return row

    existing = session.execute(
        text(
            """
            SELECT * FROM async_jobs
            WHERE idempotency_key = :idempotency_key
              AND store_id = :store_id
            """
        ),
        params,
    ).mappings().one_or_none()

    if existing is not None:
        return existing

    raise IdempotencyConflict(
        "idempotency key is already used by another store"
    )


__all__ = [
    "IdempotencyConflict",
    "InvalidJobType",
    "QueueError",
    "VALID_JOB_TYPES",
    "enqueue",
]
