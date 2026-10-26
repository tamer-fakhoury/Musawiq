"""Import batch validation orchestration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.imports.csv_reader import CsvError, read_csv
from musawiq.imports.duplicates import (
    detect_in_file_duplicates,
    split_against_existing,
)
from musawiq.imports.validation import Issue, dedupe_hash, validate_row
from musawiq.storage import get_storage


class ImportValidationError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


def _load_mapping(
    session: Session,
    tenant: TenantContext,
    batch: Mapping[str, Any],
) -> dict[str, str]:
    if not batch["column_mapping_id"]:
        raise ImportValidationError(
            "mapping_required",
            "A saved column mapping is required before validation.",
        )

    row = session.execute(
        text(
            """
            SELECT mapping FROM column_mappings
            WHERE id = :id AND store_id = :store_id
            """
        ),
        {
            "id": batch["column_mapping_id"],
            "store_id": tenant.store_id,
        },
    ).mappings().one_or_none()

    if row is None or not isinstance(row["mapping"], dict):
        raise ImportValidationError(
            "mapping_required",
            "A saved column mapping is required before validation.",
        )
    return row["mapping"]


def _load_store(
    session: Session, tenant: TenantContext
) -> Mapping[str, Any]:
    row = session.execute(
        text(
            """
            SELECT timezone, default_currency FROM stores
            WHERE id = :store_id
            """
        ),
        {"store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise ImportValidationError(
            "store_not_found", "The active store was not found."
        )
    return row


def _load_file(
    session: Session,
    tenant: TenantContext,
    batch: Mapping[str, Any],
) -> bytes:
    if batch["source_type"] != "csv":
        raise ImportValidationError(
            "invalid_source_type",
            "Only csv import batches can be validated.",
        )
    if not batch["stored_file_id"]:
        raise ImportValidationError(
            "stored_file_required",
            "The batch has no staged CSV file.",
        )

    row = session.execute(
        text(
            """
            SELECT storage_key FROM stored_files
            WHERE id = :id AND store_id = :store_id
            """
        ),
        {
            "id": batch["stored_file_id"],
            "store_id": tenant.store_id,
        },
    ).mappings().one_or_none()
    if row is None:
        raise ImportValidationError(
            "stored_file_required",
            "The batch has no staged CSV file.",
        )

    try:
        return get_storage().open(row["storage_key"])
    except FileNotFoundError as exc:
        raise ImportValidationError(
            "stored_file_required",
            "The staged CSV file is no longer available.",
        ) from exc


def _replace_previous_results(
    session: Session, tenant: TenantContext, batch_id: Any
) -> None:
    params = {"batch_id": batch_id, "store_id": tenant.store_id}
    session.execute(
        text(
            """
            DELETE FROM import_issues
            WHERE import_batch_id = :batch_id AND store_id = :store_id
            """
        ),
        params,
    )
    session.execute(
        text(
            """
            DELETE FROM import_rows
            WHERE import_batch_id = :batch_id AND store_id = :store_id
            """
        ),
        params,
    )


def _insert_issue(
    session: Session,
    tenant: TenantContext,
    batch_id: Any,
    row_id: Any,
    row_number: int,
    issue: Issue,
    severity: str,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO import_issues (
                store_id, import_batch_id, import_row_id, row_number,
                field_name, issue_code, severity, message, raw_value
            )
            VALUES (
                :store_id, :batch_id, :row_id, :row_number,
                :field_name, :issue_code, :severity, :message, :raw_value
            )
            """
        ),
        {
            "store_id": tenant.store_id,
            "batch_id": batch_id,
            "row_id": row_id,
            "row_number": row_number,
            "field_name": issue.field,
            "issue_code": issue.code,
            "severity": severity,
            "message": issue.message,
            "raw_value": issue.raw_value,
        },
    )


def validate_import_batch(
    session: Session,
    tenant: TenantContext,
    batch: Mapping[str, Any],
) -> dict[str, Any]:
    mapping = _load_mapping(session, tenant, batch)
    data = _load_file(session, tenant, batch)
    store = _load_store(session, tenant)

    try:
        parsed = read_csv(data)
    except CsvError as exc:
        raise ImportValidationError(
            "invalid_csv", str(exc), status_code=400
        ) from exc

    records: list[dict[str, Any]] = []
    for position, raw in enumerate(parsed.rows):
        row_number = parsed.row_numbers[position]
        normalized, issues = validate_row(
            raw,
            mapping,
            timezone=store["timezone"],
            default_currency=store["default_currency"],
        )
        if issues:
            status = "invalid"
            row_hash = None
        else:
            row_hash = dedupe_hash(normalized)
            normalized["dedupe_hash"] = row_hash
            status = "valid"

        records.append(
            {
                "row_number": row_number,
                "raw": raw,
                "normalized": normalized,
                "issues": issues,
                "hash": row_hash,
                "status": status,
            }
        )

    valid_records = [record for record in records if record["status"] == "valid"]
    valid_normalized = [record["normalized"] for record in valid_records]

    in_file_duplicates = detect_in_file_duplicates(valid_normalized)
    existing_hashes: set[str] = set()
    hashes = sorted(
        {
            record["hash"]
            for record in valid_records
            if record["hash"] is not None
        }
    )
    if hashes:
        existing_hashes = set(
            session.execute(
                text(
                    """
                    SELECT dedupe_hash::text FROM orders
                    WHERE store_id = :store_id
                      AND dedupe_hash::text = ANY(:hashes)
                    """
                ),
                {"store_id": tenant.store_id, "hashes": hashes},
            ).scalars().all()
        )

    _, existing_duplicate_positions = split_against_existing(
        valid_normalized, existing_hashes
    )

    duplicate_reason: dict[int, tuple[str, str]] = {}
    for position in existing_duplicate_positions:
        duplicate_reason[position] = (
            "duplicate_existing",
            "matches an existing order",
        )
    for position, first_position in in_file_duplicates.items():
        first_row_number = valid_records[first_position]["row_number"]
        duplicate_reason.setdefault(
            position,
            (
                "duplicate_in_file",
                f"duplicate of row {first_row_number} in this file",
            ),
        )

    for position, (code, message) in duplicate_reason.items():
        record = valid_records[position]
        record["status"] = "duplicate"
        record["issues"].append(
            Issue("dedupe_hash", code, message, record["hash"] or "")
        )

    counts = {
        "total": len(records),
        "valid": sum(1 for record in records if record["status"] == "valid"),
        "invalid": sum(
            1 for record in records if record["status"] == "invalid"
        ),
        "duplicate": sum(
            1 for record in records if record["status"] == "duplicate"
        ),
    }

    _replace_previous_results(session, tenant, batch["id"])

    for record in records:
        row_id = session.execute(
            text(
                """
                INSERT INTO import_rows (
                    store_id, import_batch_id, row_number, raw_data,
                    normalized_data, status, issue_count
                )
                VALUES (
                    :store_id, :batch_id, :row_number,
                    CAST(:raw_data AS jsonb), CAST(:normalized_data AS jsonb),
                    :status, :issue_count
                )
                RETURNING id
                """
            ),
            {
                "store_id": tenant.store_id,
                "batch_id": batch["id"],
                "row_number": record["row_number"],
                "raw_data": _json(record["raw"]),
                "normalized_data": _json(record["normalized"]),
                "status": record["status"],
                "issue_count": len(record["issues"]),
            },
        ).scalar_one()

        severity = (
            "warning" if record["status"] == "duplicate" else "error"
        )
        for issue in record["issues"]:
            _insert_issue(
                session,
                tenant,
                batch["id"],
                row_id,
                record["row_number"],
                issue,
                severity,
            )

    updated = session.execute(
        text(
            """
            UPDATE import_batches
            SET total_rows = :total,
                valid_rows = :valid,
                invalid_rows = :invalid,
                duplicate_rows = :duplicate,
                status = 'preview',
                started_at = now(),
                completed_at = now()
            WHERE id = :batch_id AND store_id = :store_id
            RETURNING id, status
            """
        ),
        {
            "total": counts["total"],
            "valid": counts["valid"],
            "invalid": counts["invalid"],
            "duplicate": counts["duplicate"],
            "batch_id": batch["id"],
            "store_id": tenant.store_id,
        },
    ).mappings().one()

    return {
        "batch_id": str(updated["id"]),
        "status": updated["status"],
        "counts": counts,
    }


__all__ = ["ImportValidationError", "validate_import_batch"]
