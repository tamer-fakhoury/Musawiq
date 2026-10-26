"""Import column-mapping suggestions and persistence."""

from __future__ import annotations

import uuid

from psycopg.types.json import Jsonb
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.imports.csv_reader import ParsedCsv, read_csv
from musawiq.imports.mapping import (
    missing_required,
    suggest_mapping,
)
from musawiq.repositories.base import TenantScopedRepository
from musawiq.storage import get_storage


class MappingError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _batch_csv(
    session: Session,
    batch_id: uuid.UUID | str,
) -> tuple[dict, ParsedCsv]:
    batch = TenantScopedRepository(session, "import_batches").get(batch_id)
    if batch is None:
        raise LookupError("import batch not found")

    stored_file_id = batch["stored_file_id"]
    if stored_file_id is None:
        raise LookupError("import batch has no stored file")

    stored_file = TenantScopedRepository(session, "stored_files").get(
        stored_file_id
    )
    if stored_file is None or not stored_file["storage_key"]:
        raise LookupError("stored file not found")

    data = get_storage().open(stored_file["storage_key"])
    return dict(batch), read_csv(data)


def suggest_for_batch(
    session: Session,
    tenant: TenantContext,
    batch_id: uuid.UUID | str,
) -> dict:
    _, parsed = _batch_csv(session, batch_id)
    suggested = suggest_mapping(parsed.headers)
    samples = {
        header: [row[header] for row in parsed.rows[:3]]
        for header in parsed.headers
    }
    return {
        "headers": parsed.headers,
        "suggested": suggested,
        "missing_required": sorted(missing_required(suggested)),
        "samples": samples,
    }


def save_mapping(
    session: Session,
    tenant: TenantContext,
    batch_id: uuid.UUID | str,
    mapping: dict[str, str],
    *,
    name: str | None = None,
) -> uuid.UUID:
    _, parsed = _batch_csv(session, batch_id)

    missing = missing_required(mapping)
    if missing:
        raise MappingError(
            "missing_required",
            "missing required targets: " + ", ".join(sorted(missing)),
        )

    sources = list(mapping.values())
    if len(sources) != len(set(sources)):
        raise MappingError("duplicate_source", "a source column is reused")

    unknown = sorted(set(sources) - set(parsed.headers))
    if unknown:
        raise MappingError(
            "unknown_source",
            "source column not found: " + ", ".join(unknown),
        )

    repository = TenantScopedRepository(session, "column_mappings")
    row = repository.insert(
        {
            "name": name or f"import-{batch_id}",
            "source_type": "csv",
            "mapping": Jsonb(mapping),
            "is_default": False,
            "created_by": tenant.user_id,
        }
    )
    mapping_id = uuid.UUID(str(row["id"]))

    updated = TenantScopedRepository(session, "import_batches").update(
        batch_id,
        {"column_mapping_id": mapping_id},
    )
    if updated is None:
        raise LookupError("import batch not found")
    return mapping_id


__all__ = ["MappingError", "save_mapping", "suggest_for_batch"]
