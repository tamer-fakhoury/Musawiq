"""Generic tenant-scoped repository over SQLAlchemy Core ``text()``.

There are no ORM models yet. The repository knows a table name and always adds
``store_id = <tenant>`` to every statement. Constructing or using it without a
tenant context raises ``TenantContextError`` before any SQL is built.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext, get_tenant

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


class RepositoryError(RuntimeError):
    """Base class for repository contract violations."""


class TenantScopeError(RepositoryError):
    """Raised when a caller tries to cross the active tenant scope."""


def _quote_identifier(value: str, kind: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(
            f"{kind} must be a lowercase SQL identifier, got {value!r}"
        )
    return f'"{value}"'


def _coerce_uuid(value: object, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{name} must be a valid UUID") from exc


def _filters_sql(
    filters: Mapping[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    if not filters:
        return "", {}
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for index, (column, value) in enumerate(filters.items()):
        quoted = _quote_identifier(column, "filter column")
        if value is None:
            clauses.append(f"{quoted} IS NULL")
            continue
        bind = f"filter_{index}"
        clauses.append(f"{quoted} = :{bind}")
        params[bind] = value
    return " AND " + " AND ".join(clauses), params


class TenantScopedRepository:
    """Read and write one table inside the active tenant.

    ``session`` must already have a tenant context (see
    ``musawiq.db.tenant.set_local_tenant``). The context is re-read for every
    operation so a session cannot be reused across transactions by accident.
    """

    def __init__(self, session: Session, table: str) -> None:
        self.session = session
        self.table = _quote_identifier(table, "table")
        get_tenant(session)

    def _tenant(self) -> TenantContext:
        return get_tenant(self.session)

    @property
    def _table_sql(self) -> str:
        return f"public.{self.table}"

    def list(
        self,
        *,
        filters: Mapping[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Mapping[str, Any]]:
        tenant = self._tenant()
        if not isinstance(limit, int) or limit < 1 or limit > 1000:
            raise ValueError("limit must be an integer between 1 and 1000")
        if not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a non-negative integer")

        filter_sql, params = _filters_sql(filters)
        params.update(
            {
                "tenant_store_id": tenant.store_id,
                "limit": limit,
                "offset": offset,
            }
        )
        sql = (
            f"SELECT * FROM {self._table_sql} "
            "WHERE store_id = :tenant_store_id"
            f"{filter_sql} "
            "ORDER BY id LIMIT :limit OFFSET :offset"
        )
        return list(self.session.execute(text(sql), params).mappings().all())

    def get(self, record_id: uuid.UUID | str) -> Mapping[str, Any] | None:
        tenant = self._tenant()
        record_uuid = _coerce_uuid(record_id, "id")
        sql = (
            f"SELECT * FROM {self._table_sql} "
            "WHERE id = :id AND store_id = :tenant_store_id LIMIT 1"
        )
        return (
            self.session.execute(
                text(sql),
                {"id": record_uuid, "tenant_store_id": tenant.store_id},
            )
            .mappings()
            .one_or_none()
        )

    def insert(self, values: Mapping[str, Any]) -> Mapping[str, Any]:
        tenant = self._tenant()
        if not values:
            raise ValueError("insert requires at least one column value")

        columns: list[str] = []
        placeholders: list[str] = []
        params: dict[str, Any] = {}
        for index, (column, value) in enumerate(values.items()):
            quoted = _quote_identifier(column, "column")
            if column == "store_id":
                provided = _coerce_uuid(value, "store_id")
                if provided != tenant.store_id:
                    raise TenantScopeError(
                        "insert cannot write a different store_id"
                    )
                value = provided
            bind = f"value_{index}"
            columns.append(quoted)
            placeholders.append(f":{bind}")
            params[bind] = value

        if "store_id" not in values:
            bind = f"value_{len(values)}"
            columns.append('"store_id"')
            placeholders.append(f":{bind}")
            params[bind] = tenant.store_id

        sql = (
            f"INSERT INTO {self._table_sql} ({', '.join(columns)}) "
            f"VALUES ({', '.join(placeholders)}) RETURNING *"
        )
        return self.session.execute(text(sql), params).mappings().one()

    def update(
        self,
        record_id: uuid.UUID | str,
        values: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        tenant = self._tenant()
        if not values:
            raise ValueError("update requires at least one column value")
        if "store_id" in values:
            raise TenantScopeError("update cannot change store_id")

        record_uuid = _coerce_uuid(record_id, "id")
        assignments: list[str] = []
        params: dict[str, Any] = {}
        for index, (column, value) in enumerate(values.items()):
            if column == "id":
                raise ValueError("update cannot change id")
            quoted = _quote_identifier(column, "column")
            bind = f"set_{index}"
            assignments.append(f"{quoted} = :{bind}")
            params[bind] = value

        params["id"] = record_uuid
        params["tenant_store_id"] = tenant.store_id
        sql = (
            f"UPDATE {self._table_sql} SET {', '.join(assignments)} "
            "WHERE id = :id AND store_id = :tenant_store_id RETURNING *"
        )
        return self.session.execute(text(sql), params).mappings().one_or_none()

    def delete(self, record_id: uuid.UUID | str) -> bool:
        tenant = self._tenant()
        record_uuid = _coerce_uuid(record_id, "id")
        sql = (
            f"DELETE FROM {self._table_sql} "
            "WHERE id = :id AND store_id = :tenant_store_id RETURNING id"
        )
        row = (
            self.session.execute(
                text(sql),
                {"id": record_uuid, "tenant_store_id": tenant.store_id},
            )
            .mappings()
            .first()
        )
        return row is not None


__all__ = [
    "RepositoryError",
    "TenantScopeError",
    "TenantScopedRepository",
]
