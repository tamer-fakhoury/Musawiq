"""Append-only audit trail service.

The service has one write path, :meth:`AuditService.record`. It never exposes
update or delete operations. Reads are tenant-scoped in SQL and also pass
through the PostgreSQL RLS policy installed by DB-0.15.

Request context assumptions:
    Request state carries a ``TenantContext`` at ``request.state.tenant`` and a
    correlation ID at ``request.state.correlation_id``. The current tenant
    middleware supplies both. An upstream component may supply an already
    hashed client address through ``request.state.ip_hash`` or the
    ``X-IP-Hash`` header; raw client IP headers are never read or stored.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import ROLES, TenantContext, TenantContextMissing

_IP_HASH = re.compile(r"^[0-9a-fA-F]{64}$")
_MAX_PAGE_SIZE = 200


def _coerce_uuid(value: object, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{name} must be a valid UUID") from exc


def _optional_uuid(value: object, name: str) -> uuid.UUID | None:
    if value is None:
        return None
    return _coerce_uuid(value, name)


def _correlation_uuid(value: object) -> uuid.UUID:
    if value is None:
        return uuid.uuid4()
    return _coerce_uuid(value, "correlation_id")


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _utc(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_ip_hash(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not _IP_HASH.fullmatch(value):
        raise ValueError("ip_hash must be a 64-character hexadecimal SHA-256")
    return value.lower()


@dataclass(frozen=True)
class AuditFilters:
    date_from: datetime | None = None
    date_to: datetime | None = None
    actor_user_id: uuid.UUID | str | None = None
    target_type: str | None = None
    target_id: uuid.UUID | str | None = None
    action: str | None = None

    def normalized(self) -> "AuditFilters":
        start = _utc(self.date_from, "date_from")
        end = _utc(self.date_to, "date_to")
        if start is not None and end is not None and start > end:
            raise ValueError("date_from must not be after date_to")
        return AuditFilters(
            date_from=start,
            date_to=end,
            actor_user_id=_optional_uuid(self.actor_user_id, "actor_user_id"),
            target_type=(
                _required_text(self.target_type, "target_type")
                if self.target_type is not None
                else None
            ),
            target_id=_optional_uuid(self.target_id, "target_id"),
            action=(
                _required_text(self.action, "action")
                if self.action is not None
                else None
            ),
        )

    def clause(self) -> tuple[str, dict[str, Any]]:
        normalized = self.normalized()
        clauses = ["store_id = :tenant_store_id"]
        params: dict[str, Any] = {}
        if normalized.date_from is not None:
            clauses.append("created_at >= :date_from")
            params["date_from"] = normalized.date_from
        if normalized.date_to is not None:
            clauses.append("created_at <= :date_to")
            params["date_to"] = normalized.date_to
        if normalized.actor_user_id is not None:
            clauses.append("actor_user_id = :actor_user_id")
            params["actor_user_id"] = normalized.actor_user_id
        if normalized.target_type is not None:
            clauses.append("target_type = :target_type")
            params["target_type"] = normalized.target_type
        if normalized.target_id is not None:
            clauses.append("target_id = :target_id")
            params["target_id"] = normalized.target_id
        if normalized.action is not None:
            clauses.append("action = :action")
            params["action"] = normalized.action
        return " AND ".join(clauses), params


@dataclass(frozen=True)
class AuditPage:
    items: tuple[Mapping[str, Any], ...]
    total: int
    limit: int
    offset: int


class AuditService:
    """Read and append audit rows for one tenant request.

    Construct with :meth:`from_request` inside an HTTP handler, or directly
    with a ``TenantContext`` from a background job. The service never commits;
    the caller's transaction controls durability and atomicity.
    """

    def __init__(
        self,
        session: Session,
        tenant: TenantContext,
        *,
        correlation_id: object = None,
        ip_hash: object = None,
        user_agent: str | None = None,
    ) -> None:
        if not isinstance(tenant, TenantContext):
            raise TenantContextMissing("audit service requires a TenantContext")
        if tenant.role not in ROLES:
            raise ValueError(f"role must be one of {sorted(ROLES)}")
        self.session = session
        self.tenant = tenant
        self.correlation_id = _correlation_uuid(correlation_id)
        self.ip_hash = _normalize_ip_hash(ip_hash)
        self.user_agent = user_agent

    @classmethod
    def from_request(cls, request: Any, session: Session) -> "AuditService":
        tenant = getattr(request.state, "tenant", None)
        if not isinstance(tenant, TenantContext):
            raise TenantContextMissing(
                "request has no tenant context; tenant middleware did not run"
            )
        correlation_id = getattr(request.state, "correlation_id", None)
        ip_hash = getattr(request.state, "ip_hash", None)
        if ip_hash is None:
            ip_hash = request.headers.get("X-IP-Hash")
        return cls(
            session,
            tenant,
            correlation_id=correlation_id,
            ip_hash=ip_hash,
            user_agent=request.headers.get("user-agent"),
        )

    def record(
        self,
        *,
        action: str,
        target_type: str,
        target_id: uuid.UUID | str | None,
        before: Any = None,
        after: Any = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Append one audit row and return its id and timestamp."""
        action_value = _required_text(action, "action")
        target_type_value = _required_text(target_type, "target_type")
        target_uuid = _optional_uuid(target_id, "target_id")
        metadata_value = dict(metadata or {})
        metadata_value.setdefault("schema_version", 1)

        row = self.session.execute(
            text(
                """
                INSERT INTO public.audit_logs (
                    store_id, actor_user_id, actor_type, action,
                    target_type, target_id, before, after, metadata,
                    ip_hash, user_agent, correlation_id
                ) VALUES (
                    :store_id, :actor_user_id, 'user', :action,
                    :target_type, :target_id, :before, :after, :metadata,
                    :ip_hash, :user_agent, :correlation_id
                )
                RETURNING id, created_at
                """
            ),
            {
                "store_id": self.tenant.store_id,
                "actor_user_id": self.tenant.user_id,
                "action": action_value,
                "target_type": target_type_value,
                "target_id": target_uuid,
                "before": Jsonb(before) if before is not None else None,
                "after": Jsonb(after) if after is not None else None,
                "metadata": Jsonb(metadata_value),
                "ip_hash": self.ip_hash,
                "user_agent": self.user_agent,
                "correlation_id": self.correlation_id,
            },
        ).mappings().one()
        return dict(row)

    def list_logs(
        self,
        filters: AuditFilters | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> AuditPage:
        if not isinstance(limit, int) or limit < 1 or limit > _MAX_PAGE_SIZE:
            raise ValueError(
                f"limit must be an integer between 1 and {_MAX_PAGE_SIZE}"
            )
        if not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a non-negative integer")

        query = (filters or AuditFilters()).normalized()
        where, params = query.clause()
        params["tenant_store_id"] = self.tenant.store_id
        params["limit"] = limit
        params["offset"] = offset

        total = self.session.execute(
            text(
                "SELECT count(*) FROM public.audit_logs "
                f"WHERE {where}"
            ),
            {key: value for key, value in params.items() if key not in {"limit", "offset"}},
        ).scalar_one()

        rows = self.session.execute(
            text(
                "SELECT id, created_at, store_id, actor_user_id, actor_type, "
                "action, target_type, target_id, before, after, metadata, "
                "correlation_id "
                "FROM public.audit_logs "
                f"WHERE {where} "
                "ORDER BY created_at DESC, id DESC "
                "LIMIT :limit OFFSET :offset"
            ),
            params,
        ).mappings().all()
        return AuditPage(tuple(rows), int(total), limit, offset)

    def export_logs(
        self, filters: AuditFilters | None = None
    ) -> tuple[Mapping[str, Any], ...]:
        where, params = (filters or AuditFilters()).normalized().clause()
        params["tenant_store_id"] = self.tenant.store_id
        rows = self.session.execute(
            text(
                "SELECT id, created_at, store_id, actor_user_id, actor_type, "
                "action, target_type, target_id, before, after, metadata, "
                "correlation_id "
                "FROM public.audit_logs "
                f"WHERE {where} "
                "ORDER BY created_at ASC, id ASC"
            ),
            params,
        ).mappings().all()
        return tuple(rows)


__all__ = [
    "AuditFilters",
    "AuditPage",
    "AuditService",
]
