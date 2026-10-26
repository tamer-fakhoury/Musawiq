"""Tenant context and transaction-local tenant settings.

The application sets ``app.store_id`` and ``app.user_id`` with ``SET LOCAL`` so
the values expire with the current transaction. The DB-0.15 forced RLS policies
read the same settings; the Python context mirrors them for repositories.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import event, text
from sqlalchemy.orm import Session


class TenantContextError(RuntimeError):
    """Base class for tenant-context contract violations."""


class TenantContextMissing(TenantContextError):
    """Raised when a tenant-scoped query has no active tenant context."""


ROLES = frozenset({"owner", "manager", "analyst"})


@dataclass(frozen=True)
class TenantContext:
    store_id: uuid.UUID
    user_id: uuid.UUID
    role: str = "analyst"


def _coerce_uuid(value: object, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{name} must be a valid UUID") from exc


def set_local_tenant(
    session: Session,
    store_id: uuid.UUID | str,
    user_id: uuid.UUID | str,
    role: str = "analyst",
) -> TenantContext:
    """Set the transaction-local tenant settings and return the context.

    PostgreSQL does not accept bind parameters in ``SET`` statements, so the
    validated UUID values are interpolated as literals. They are canonicalised
    by ``uuid.UUID`` first, which keeps the statement injection-safe.
    """
    store_uuid = _coerce_uuid(store_id, "store_id")
    user_uuid = _coerce_uuid(user_id, "user_id")
    normalized_role = role.strip().lower()
    if normalized_role not in ROLES:
        raise ValueError(f"role must be one of {sorted(ROLES)}")

    session.execute(text(f"SET LOCAL app.store_id = '{store_uuid}'"))
    session.execute(text(f"SET LOCAL app.user_id = '{user_uuid}'"))

    context = TenantContext(
        store_id=store_uuid,
        user_id=user_uuid,
        role=normalized_role,
    )
    session.info["tenant"] = context
    return context


def get_tenant(session: Session) -> TenantContext:
    context = session.info.get("tenant")
    if not isinstance(context, TenantContext):
        raise TenantContextMissing(
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
