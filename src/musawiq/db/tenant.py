"""Tenant context and transaction-local tenant settings.

The application sets ``app.store_id`` and ``app.user_id`` with ``SET LOCAL`` so
the values expire with the current transaction. DB-0.15 will use the same
settings in RLS policies; wiring them now keeps the application contract stable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import event, text
from sqlalchemy.orm import Session


class TenantContextError(RuntimeError):
    """Raised when code tries to use a repository without a tenant context."""


@dataclass(frozen=True)
class TenantContext:
    store_id: uuid.UUID
    user_id: uuid.UUID


def _coerce_uuid(value: object, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{name} must be a valid UUID") from exc


def set_local_tenant(
    session: Session,
    store_id: uuid.UUID | str,
    user_id: uuid.UUID | str,
) -> TenantContext:
    """Set the transaction-local tenant settings and return the context.

    PostgreSQL does not accept bind parameters in ``SET`` statements, so the
    validated UUID values are interpolated as literals. They are canonicalised
    by ``uuid.UUID`` first, which keeps the statement injection-safe.
    """
    store_uuid = _coerce_uuid(store_id, "store_id")
    user_uuid = _coerce_uuid(user_id, "user_id")

    session.execute(text(f"SET LOCAL app.store_id = '{store_uuid}'"))
    session.execute(text(f"SET LOCAL app.user_id = '{user_uuid}'"))

    context = TenantContext(store_id=store_uuid, user_id=user_uuid)
    session.info["tenant"] = context
    return context


def get_tenant(session: Session) -> TenantContext:
    context = session.info.get("tenant")
    if not isinstance(context, TenantContext):
        raise TenantContextError(
            "Tenant context is not set; call "
            "set_local_tenant(session, store_id, user_id) inside the current "
            "transaction before using a tenant-scoped repository"
        )
    return context


def clear_tenant(session: Session) -> None:
    session.info.pop("tenant", None)


@event.listens_for(Session, "after_transaction_end")
def _clear_tenant_after_transaction(
    session: Session, transaction: object
) -> None:
    """Drop the Python context when the root transaction ends.

    ``SET LOCAL`` expires with the transaction, so keeping the Python context
    would be misleading. Nested savepoints do not clear it.
    """
    if getattr(transaction, "parent", None) is None:
        session.info.pop("tenant", None)
