"""Import preview counts, rows, issues, and error-report bytes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.imports.reports import error_report_csv, summarize


class ImportPreviewError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True)
class _ReportIssue:
    row_number: int
    field: str
    code: str
    message: str
    raw_value: str


def _batch(
    session: Session,
    tenant: TenantContext,
    batch_id: uuid.UUID | str,
) -> dict[str, Any]:
    row = (
        session.execute(
            text(
                """
                SELECT id, status, total_rows, valid_rows, invalid_rows,
                       duplicate_rows
                FROM import_batches
                WHERE id = :batch_id AND store_id = :store_id
                """
            ),
            {"batch_id": batch_id, "store_id": tenant.store_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise ImportPreviewError(
            "not_found", "Resource not found.", 404
        )
    return dict(row)


def _issue_item(row: Any) -> dict[str, Any]:
    return {
        "row_number": row["row_number"],
        "field": row["field_name"],
        "code": row["issue_code"],
        "message": row["message"],
        "raw_value": row["raw_value"],
    }


def preview_batch(
    session: Session,
    tenant: TenantContext,
    batch_id: uuid.UUID | str,
    *,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    batch = _batch(session, tenant, batch_id)
    if batch["status"] != "preview":
        raise ImportPreviewError(
            "not_validated",
            "Import batch must be validated before preview.",
            409,
        )

    counts = summarize(
        batch["total_rows"],
        batch["valid_rows"],
        batch["invalid_rows"],
        batch["duplicate_rows"],
    )

    rows = session.execute(
        text(
            """
            SELECT row_number, status
            FROM import_rows
            WHERE store_id = :store_id
              AND import_batch_id = :batch_id
              AND status = 'valid'
            ORDER BY row_number
            LIMIT :limit
            """
        ),
        {
            "store_id": tenant.store_id,
            "batch_id": batch_id,
            "limit": limit,
        },
    ).mappings().all()

    issues_total = session.execute(
        text(
            """
            SELECT count(*)
            FROM import_issues
            WHERE store_id = :store_id AND import_batch_id = :batch_id
            """
        ),
        {"store_id": tenant.store_id, "batch_id": batch_id},
    ).scalar_one()

    issues = session.execute(
        text(
            """
            SELECT row_number, field_name, issue_code, message, raw_value
            FROM import_issues
            WHERE store_id = :store_id AND import_batch_id = :batch_id
            ORDER BY row_number, id
            LIMIT :limit OFFSET :offset
            """
        ),
        {
            "store_id": tenant.store_id,
            "batch_id": batch_id,
            "limit": limit,
            "offset": offset,
        },
    ).mappings().all()

    return {
        "counts": counts,
        "rows": [
            {"row_number": row["row_number"], "status": row["status"]}
            for row in rows
        ],
        "issues": {
            "items": [_issue_item(row) for row in issues],
            "total": int(issues_total),
            "limit": limit,
            "offset": offset,
        },
    }


def error_report(
    session: Session,
    tenant: TenantContext,
    batch_id: uuid.UUID | str,
) -> bytes:
    _batch(session, tenant, batch_id)
    rows = session.execute(
        text(
            """
            SELECT row_number, field_name, issue_code, message, raw_value
            FROM import_issues
            WHERE store_id = :store_id AND import_batch_id = :batch_id
            ORDER BY row_number, id
            """
        ),
        {"store_id": tenant.store_id, "batch_id": batch_id},
    ).mappings().all()

    issues = [
        _ReportIssue(
            row_number=row["row_number"],
            field=row["field_name"] or "",
            code=row["issue_code"],
            message=row["message"],
            raw_value=row["raw_value"] or "",
        )
        for row in rows
    ]
    return error_report_csv(issues)


__all__ = [
    "ImportPreviewError",
    "error_report",
    "preview_batch",
]
