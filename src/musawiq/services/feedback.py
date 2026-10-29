"""Manual and file-based customer feedback intake.

Accepted files are UTF-8 ``.csv`` and ``.txt`` files and binary ``.xlsx``
workbooks, up to the shared 20 MB upload limit. CSV and XLSX inputs may use a
header row with ``text`` and optional ``language``, ``sentiment``, and
``captured_at`` columns. Without a header, the first column is feedback text.
TXT inputs use one non-empty line per item.

Validation errors identify the file and row number only. Submitted feedback
text is never echoed in an error response.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
import zipfile
from collections.abc import Mapping
from datetime import datetime, time, timezone
from typing import Any
from xml.etree import ElementTree

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.repositories.base import TenantScopedRepository
from musawiq.repositories.feedback_items import FeedbackItemRepository
from musawiq.storage import get_storage
from musawiq.storage.local import DEFAULT_MAX_SIZE_BYTES

MAX_FEEDBACK_BYTES = DEFAULT_MAX_SIZE_BYTES
MAX_FEEDBACK_ITEMS = 10_000
FEEDBACK_FILE_PURPOSE = "feedback_file"
SENTIMENTS = frozenset({"positive", "neutral", "negative"})
CSV_CONTENT_TYPE = "text/csv"
TEXT_CONTENT_TYPE = "text/plain"
XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
_ALLOWED_FILES = {
    "csv": CSV_CONTENT_TYPE,
    "txt": TEXT_CONTENT_TYPE,
    "xlsx": XLSX_CONTENT_TYPE,
}
_TEXT_HEADERS = frozenset(
    {"text", "feedback", "feedback_text", "comment", "message"}
)
_OPTIONAL_HEADERS = {
    "language": "language",
    "sentiment": "sentiment",
    "captured_at": "captured_at",
    "captured": "captured_at",
    "date": "captured_at",
}
_XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


class FeedbackError(Exception):
    """Base class for feedback contract failures."""


class FeedbackValidationError(FeedbackError):
    """Raised when feedback input is rejected."""

    def __init__(self, fields: Mapping[str, str]) -> None:
        self.fields = dict(fields)
        super().__init__("Feedback validation failed.")


def _iso(value: object) -> str | None:
    return value.isoformat() if value is not None else None


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise FeedbackValidationError({field: f"{field} must be a string"})
    result = value.strip()
    return result or None


def _sentiment(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or value.strip().lower() not in SENTIMENTS:
        raise FeedbackValidationError(
            {"sentiment": "sentiment must be positive, neutral, or negative"}
        )
    return value.strip().lower()


def _captured_at(value: object, field: str = "captured_at") -> datetime:
    if value is None or value == "":
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        raw = value.strip()
        try:
            if len(raw) == 10:
                parsed_date = datetime.strptime(raw, "%Y-%m-%d").date()
                result = datetime.combine(parsed_date, time.min)
            else:
                result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise FeedbackValidationError(
                {field: f"{field} must be an ISO date or datetime"}
            ) from exc
    else:
        raise FeedbackValidationError(
            {field: f"{field} must be an ISO date or datetime"}
        )
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def _manual_text(payload: Mapping[str, Any]) -> str:
    text_value = payload.get("text")
    if not isinstance(text_value, str) or not text_value.strip():
        raise FeedbackValidationError({"text": "text is required"})
    return text_value.strip()


def _feedback_out(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "store_id": str(row["store_id"]),
        "audience_profile_id": (
            str(row["audience_profile_id"])
            if row["audience_profile_id"] is not None
            else None
        ),
        "source": row["source"],
        "stored_file_id": (
            str(row["stored_file_id"])
            if row["stored_file_id"] is not None
            else None
        ),
        "text": row["text"],
        "language": row["language"],
        "sentiment": row["sentiment"],
        "captured_at": _iso(row["captured_at"]),
        "created_at": _iso(row["created_at"]),
    }


def _stored_file_out(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "purpose": row["purpose"],
        "original_filename": row["original_filename"],
        "mime_type": row["mime_type"],
        "size_bytes": row["size_bytes"],
        "status": row["status"],
    }


def _current_audience_profile_id(
    session: Session, tenant: TenantContext
) -> uuid.UUID | None:
    row = session.execute(
        text(
            """
            SELECT id FROM audience_profiles
            WHERE store_id = :store_id AND is_current
            LIMIT 1
            """
        ),
        {"store_id": tenant.store_id},
    ).first()
    return row[0] if row is not None else None


def _linked_profile_id(
    session: Session,
    tenant: TenantContext,
    audience_profile_id: object,
) -> uuid.UUID | None:
    if audience_profile_id is None or audience_profile_id == "":
        return _current_audience_profile_id(session, tenant)
    try:
        profile_id = uuid.UUID(str(audience_profile_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise FeedbackValidationError(
            {"audience_profile_id": "audience_profile_id must be a valid UUID"}
        ) from exc
    exists = session.execute(
        text(
            """
            SELECT 1 FROM audience_profiles
            WHERE id = :id AND store_id = :store_id
            """
        ),
        {"id": profile_id, "store_id": tenant.store_id},
    ).first()
    if exists is None:
        raise FeedbackValidationError(
            {
                "audience_profile_id": (
                    "audience_profile_id must reference a profile in this store"
                )
            }
        )
    return profile_id


def _save_feedback_file(
    session: Session,
    tenant: TenantContext,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    item_count: int,
) -> Mapping[str, Any]:
    try:
        stored = get_storage().save(
            data,
            filename=filename,
            content_type=content_type,
            purpose=FEEDBACK_FILE_PURPOSE,
        )
    except ValueError as exc:
        raise FeedbackValidationError({"file": str(exc)}) from exc

    return TenantScopedRepository(session, "stored_files").insert(
        {
            "purpose": FEEDBACK_FILE_PURPOSE,
            "original_filename": stored.original_filename,
            "mime_type": stored.content_type,
            "size_bytes": stored.size_bytes,
            "checksum_sha256": stored.checksum_sha256,
            "storage_provider": "local",
            "storage_key": stored.key,
            "status": "committed",
            "uploaded_by_user_id": tenant.user_id,
            "metadata": Jsonb(
                {"schema_version": 1, "feedback_item_count": item_count}
            ),
        }
    )


def submit_feedback(
    session: Session,
    tenant: TenantContext,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Store one manually entered feedback item."""

    if not isinstance(payload, Mapping):
        raise FeedbackValidationError({"body": "body must be an object"})
    values = {
        "text": _manual_text(payload),
        "language": _optional_text(payload.get("language"), "language"),
        "sentiment": _sentiment(payload.get("sentiment")),
        "captured_at": _captured_at(payload.get("captured_at")),
    }
    profile_id = _linked_profile_id(
        session, tenant, payload.get("audience_profile_id")
    )
    row = FeedbackItemRepository(session).insert_item(
        {
            **values,
            "audience_profile_id": profile_id,
            "source": "manual",
            "stored_file_id": None,
        }
    )
    return _feedback_out(row)


def _normalized_content_type(value: str) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


def _file_kind(filename: str, content_type: str) -> str:
    lower = (filename or "").lower()
    if "." not in lower:
        raise FeedbackValidationError(
            {"file": "file must have a .csv, .txt, or .xlsx extension"}
        )
    extension = lower.rsplit(".", 1)[-1]
    expected = _ALLOWED_FILES.get(extension)
    if expected is None:
        raise FeedbackValidationError(
            {"file": "unsupported file type; use .csv, .txt, or .xlsx"}
        )
    if _normalized_content_type(content_type) != expected:
        raise FeedbackValidationError(
            {
                "file": (
                    f"{extension} files must use content type {expected}"
                )
            }
        )
    return extension


def _decode_text_file(data: bytes) -> str:
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FeedbackValidationError(
            {"file": "file must be UTF-8 encoded"}
        ) from exc
    if not decoded.strip():
        raise FeedbackValidationError({"file": "file is empty"})
    return decoded


def _normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _column_index(column: str) -> int:
    result = 0
    for char in column:
        result = result * 26 + (ord(char.upper()) - 64)
    return result - 1


def _xlsx_rows(data: bytes) -> list[list[str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            shared: list[str] = []
            if "xl/sharedStrings.xml" in names:
                root = ElementTree.fromstring(
                    archive.read("xl/sharedStrings.xml")
                )
                for item in root.iter(f"{_XLSX_NS}si"):
                    shared.append(
                        "".join(
                            node.text or ""
                            for node in item.iter(f"{_XLSX_NS}t")
                        )
                    )
            sheet_name = (
                "xl/worksheets/sheet1.xml"
                if "xl/worksheets/sheet1.xml" in names
                else next(
                    (
                        name
                        for name in sorted(names)
                        if name.startswith("xl/worksheets/")
                        and name.endswith(".xml")
                    ),
                    None,
                )
            )
            if sheet_name is None:
                raise FeedbackValidationError(
                    {"file": "file is not a valid .xlsx workbook"}
                )
            sheet = ElementTree.fromstring(archive.read(sheet_name))
    except (
        zipfile.BadZipFile,
        KeyError,
        IndexError,
        ValueError,
        ElementTree.ParseError,
    ) as exc:
        raise FeedbackValidationError(
            {"file": "file is not a valid .xlsx workbook"}
        ) from exc

    rows: list[list[str]] = []
    for row in sheet.iter(f"{_XLSX_NS}row"):
        values: dict[int, str] = {}
        next_index = 0
        for cell in row.findall(f"{_XLSX_NS}c"):
            reference = cell.get("r", "")
            match = re.match(r"([A-Z]+)", reference)
            index = _column_index(match.group(1)) if match else next_index
            cell_type = cell.get("t")
            if cell_type == "s":
                raw = cell.find(f"{_XLSX_NS}v")
                if raw is not None and raw.text is not None:
                    value = shared[int(raw.text)]
                else:
                    value = ""
            elif cell_type == "inlineStr":
                value = "".join(
                    node.text or ""
                    for node in cell.iter(f"{_XLSX_NS}t")
                )
            else:
                raw = cell.find(f"{_XLSX_NS}v")
                value = raw.text if raw is not None and raw.text else ""
            values[index] = value
            next_index = index + 1
        if values:
            rows.append(
                [values.get(index, "") for index in range(max(values) + 1)]
            )
    return rows


def _csv_rows(data: bytes) -> list[list[str]]:
    text_value = _decode_text_file(data)
    try:
        return list(
            csv.reader(
                io.StringIO(text_value, newline=""),
                strict=True,
            )
        )
    except csv.Error as exc:
        raise FeedbackValidationError(
            {"file": "file is not valid CSV"}
        ) from exc


def _text_rows(data: bytes) -> list[list[str]]:
    return [[line] for line in _decode_text_file(data).splitlines()]


def _rows_to_items(rows: list[list[str]], *, start_row: int = 1) -> list[dict]:
    non_empty = [
        (index + start_row, row)
        for index, row in enumerate(rows)
        if any(cell.strip() for cell in row)
    ]
    if not non_empty:
        raise FeedbackValidationError({"file": "file contains no feedback"})

    header_row_number, first_row = non_empty[0]
    headers = [_normalized_header(cell) for cell in first_row]
    text_index = next(
        (index for index, header in enumerate(headers) if header in _TEXT_HEADERS),
        None,
    )
    header = text_index is not None
    if header:
        data_rows = non_empty[1:]
        optional = {
            field: next(
                (
                    index
                    for index, name in enumerate(headers)
                    if _OPTIONAL_HEADERS.get(name) == field
                ),
                None,
            )
            for field in ("language", "sentiment", "captured_at")
        }
    else:
        text_index = 0
        data_rows = non_empty
        optional = {"language": None, "sentiment": None, "captured_at": None}

    if len(data_rows) > MAX_FEEDBACK_ITEMS:
        raise FeedbackValidationError(
            {"file": f"file exceeds {MAX_FEEDBACK_ITEMS} feedback items"}
        )

    items: list[dict] = []
    errors: list[str] = []
    for row_number, row in data_rows:
        cell = lambda index: (
            row[index] if index is not None and index < len(row) else ""
        )
        text_value = cell(text_index).strip()
        if not text_value:
            errors.append(f"row {row_number}: text is required")
            continue
        try:
            sentiment = _sentiment(cell(optional["sentiment"]))
            captured_at = _captured_at(cell(optional["captured_at"]))
        except FeedbackValidationError as exc:
            for field, message in exc.fields.items():
                errors.append(f"row {row_number}: {message}")
            continue
        items.append(
            {
                "text": text_value,
                "language": _optional_text(
                    cell(optional["language"]), "language"
                ),
                "sentiment": sentiment,
                "captured_at": captured_at,
            }
        )
    if errors:
        raise FeedbackValidationError({"file": "; ".join(errors)})
    return items


def _parse_feedback_file(
    filename: str, content_type: str, data: bytes
) -> tuple[str, list[dict], str]:
    kind = _file_kind(filename, content_type)
    if not data:
        raise FeedbackValidationError({"file": "file is empty"})
    if len(data) > MAX_FEEDBACK_BYTES:
        raise FeedbackValidationError(
            {"file": "file must be 20 MB or smaller"}
        )
    if kind == "txt":
        items = _rows_to_items(_text_rows(data))
    elif kind == "csv":
        items = _rows_to_items(_csv_rows(data))
    else:
        items = _rows_to_items(_xlsx_rows(data))
    return kind, items, _ALLOWED_FILES[kind]


def upload_feedback_file(
    session: Session,
    tenant: TenantContext,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    audience_profile_id: object = None,
) -> dict[str, Any]:
    """Validate and import a feedback file, returning the stored items."""

    kind, items, normalized_type = _parse_feedback_file(
        filename, content_type, data
    )
    profile_id = _linked_profile_id(session, tenant, audience_profile_id)
    stored = _save_feedback_file(
        session,
        tenant,
        filename=filename,
        content_type=normalized_type,
        data=data,
        item_count=len(items),
    )
    repository = FeedbackItemRepository(session)
    inserted = [
        _feedback_out(
            repository.insert_item(
                {
                    **item,
                    "audience_profile_id": profile_id,
                    "source": "file",
                    "stored_file_id": stored["id"],
                }
            )
        )
        for item in items
    ]
    return {
        "file": _stored_file_out(stored),
        "items": inserted,
        "count": len(inserted),
        "format": kind,
    }


def list_feedback(
    session: Session,
    tenant: TenantContext,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise FeedbackValidationError(
            {"limit": "limit must be an integer between 1 and 500"}
        )
    if limit < 1 or limit > 500:
        raise FeedbackValidationError(
            {"limit": "limit must be an integer between 1 and 500"}
        )
    if (
        not isinstance(offset, int)
        or isinstance(offset, bool)
        or offset < 0
    ):
        raise FeedbackValidationError(
            {"offset": "offset must be a non-negative integer"}
        )
    rows = FeedbackItemRepository(session).list_items(
        limit=limit, offset=offset
    )
    return [_feedback_out(row) for row in rows]


__all__ = [
    "FeedbackError",
    "FeedbackValidationError",
    "MAX_FEEDBACK_BYTES",
    "MAX_FEEDBACK_ITEMS",
    "list_feedback",
    "submit_feedback",
    "upload_feedback_file",
]
