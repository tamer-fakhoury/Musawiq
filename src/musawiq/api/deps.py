"""Tenant-aware FastAPI dependencies."""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from musawiq.db.session import get_session_factory
from musawiq.db.tenant import (
    TenantContext,
    TenantContextMissing,
    set_local_tenant,
)
from musawiq.middleware.tenant import error_envelope, get_correlation_id
from musawiq.repositories.audit import record_cross_store_denial
from musawiq.repositories.base import TenantScopedRepository


def get_tenant(request: Request) -> TenantContext:
    """Return the tenant resolved by ``TenantMiddleware``."""
    tenant = getattr(request.state, "tenant", None)
    if not isinstance(tenant, TenantContext):
        raise TenantContextMissing(
            "Request has no tenant context; tenant middleware did not run"
        )
    return tenant


def get_session(
    tenant: TenantContext = Depends(get_tenant),
) -> Iterator[Session]:
    """Yield a request session with transaction-local tenant settings.

    The settings are applied immediately after the transaction begins, before
    any endpoint code can execute a tenant-table query. RLS then sees
    ``app.store_id`` and ``app.user_id`` for every statement in the request.
    """
    session = get_session_factory()()
    try:
        session.begin()
        set_local_tenant(
            session,
            tenant.store_id,
            tenant.user_id,
            tenant.role,
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_owned_or_404(
    repository: TenantScopedRepository,
    record_id: uuid.UUID | str,
    *,
    target_type: str,
    tenant: TenantContext,
    request: Request,
) -> Mapping[str, Any]:
    """Fetch a tenant row or raise a non-leaking 404.

    If the id exists under another store, append the security audit event first.
    The audit uses its own transaction so the 404 rollback cannot discard it.
    """
    row = repository.get(record_id)
    if row is not None:
        return row

    correlation_id = get_correlation_id(request)
    if repository.exists_in_other_store(record_id):
        record_cross_store_denial(
            tenant,
            target_type=target_type,
            target_id=record_id,
            correlation_id=correlation_id,
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=error_envelope(
            "not_found",
            "Resource not found",
            correlation_id,
        ),
    )


__all__ = [
    "get_owned_or_404",
    "get_session",
    "get_tenant",
]
