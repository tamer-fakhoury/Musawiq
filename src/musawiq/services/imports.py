"""Import upload and batch queries."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.storage import get_storage

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
CSV_CONTENT_TYPE = "text/csv"


class ImportUploadError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _content_type(value: str) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


def _validate_upload(filename: str, content_type: str, data: bytes) -> None:
    if not filename.lower().endswith(".csv") or _content_type(content_type) != CSV_CONTENT_TYPE:
        raise ImportUploadError(
            "invalid_file_type",
            "Only .csv files with content type text/csv are supported.",
        )
    if not data:
        raise ImportUploadError("empty_file", "The CSV file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImportUploadError(
            "file_too_large", "CSV files must be 20 MB or smaller."
        )
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportUploadError(
            "invalid_encoding", "CSV files must be UTF-8 encoded."
        ) from exc
    if not decoded.strip():
        raise ImportUploadError("empty_file", "The CSV file is empty.")


def create_import_batch(
    session: Session,
    tenant: TenantContext,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    strict_mode: bool,
) -> dict[str, Any]:
    _validate_upload(filename, content_type, data)

    stored = get_storage().save(
        data,
        filename=filename,
        content_type=CSV_CONTENT_TYPE,
        purpose="sales_csv",
    )

    stored_file_id = session.execute(
        text(
            """
            INSERT INTO stored_files (
                store_id, purpose, original_filename, mime_type, size_bytes,
                checksum_sha256, storage_provider, storage_key, status,
                uploaded_by_user_id
            )
            VALUES (
                :store_id, 'sales_csv', :original_filename, :mime_type,
                :size_bytes, :checksum_sha256, 'local', :storage_key,
                'staged', :uploaded_by_user_id
            )
            RETURNING id
            """
        ),
        {
            "store_id": tenant.store_id,
            "original_filename": stored.original_filename,
            "mime_type": stored.content_type,
            "size_bytes": stored.size_bytes,
            "checksum_sha256": stored.checksum_sha256,
            "storage_key": stored.key,
            "uploaded_by_user_id": tenant.user_id,
        },
    ).scalar_one()

    batch = session.execute(
        text(
            """
            INSERT INTO import_batches (
                store_id, source_type, stored_file_id, status, strict_mode,
                created_by
            )
            VALUES (
                :store_id, 'csv', :stored_file_id, 'uploaded', :strict_mode,
                :created_by
            )
            RETURNING id, status
            """
        ),
        {
            "store_id": tenant.store_id,
            "stored_file_id": stored_file_id,
            "strict_mode": strict_mode,
            "created_by": tenant.user_id,
        },
    ).mappings().one()

    return {
        "batch_id": str(batch["id"]),
        "status": batch["status"],
        "file": {
            "size_bytes": stored.size_bytes,
            "checksum_sha256": stored.checksum_sha256,
        },
    }


def batch_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    created_at = row["created_at"]
    return {
        "id": str(row["id"]),
        "status": row["status"],
        "total_rows": row["total_rows"],
        "valid_rows": row["valid_rows"],
        "invalid_rows": row["invalid_rows"],
        "duplicate_rows": row["duplicate_rows"],
        "created_at": (
            created_at.isoformat()
            if isinstance(created_at, datetime)
            else created_at
        ),
    }


def list_import_batches(
    session: Session, tenant: TenantContext
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT id, status, total_rows, valid_rows, invalid_rows,
                   duplicate_rows, created_at
            FROM import_batches
            WHERE store_id = :store_id
            ORDER BY created_at DESC, id DESC
            """
        ),
        {"store_id": tenant.store_id},
    ).mappings().all()
    return [batch_summary(row) for row in rows]


__all__ = [
    "ImportUploadError",
    "batch_summary",
    "create_import_batch",
    "list_import_batches",
]
