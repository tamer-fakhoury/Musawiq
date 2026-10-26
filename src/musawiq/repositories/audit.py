"""Security-audit writes for tenant-scoped requests.

P1-A4 will introduce the full audit service. This module contains only the
cross-store denial event required by P1-A2. It uses a separate short transaction
so the audit survives when the request transaction is rolled back by a 404.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text

from musawiq.db.session import get_session_factory
from musawiq.db.tenant import TenantContext, set_local_tenant

logger = logging.getLogger(__name__)

CROSS_STORE_ACTION = "security.cross_store_denied"


def _correlation_uuid(value: str | uuid.UUID | None) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    if value:
        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError):
            pass
    return uuid.uuid4()


def record_cross_store_denial(
    tenant: TenantContext,
    *,
    target_type: str,
    target_id: uuid.UUID | str,
    correlation_id: str | uuid.UUID | None,
) -> None:
    """Append one security event; never leak the denied row's data."""
    target_uuid = uuid.UUID(str(target_id))
    correlation_uuid = _correlation_uuid(correlation_id)
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "target_type": target_type,
        "target_id": str(target_uuid),
        "correlation_id": str(correlation_uuid),
    }

    session = get_session_factory()()
    try:
        session.begin()
        set_local_tenant(
            session,
            tenant.store_id,
            tenant.user_id,
            tenant.role,
        )
        session.execute(
            text(
                """
                INSERT INTO public.audit_logs (
                    store_id, actor_user_id, actor_type, action,
                    target_type, target_id, metadata, correlation_id
                ) VALUES (
                    :store_id, :actor_user_id, 'user', :action,
                    :target_type, :target_id, :metadata, :correlation_id
                )
                """
            ),
            {
                "store_id": tenant.store_id,
                "actor_user_id": tenant.user_id,
                "action": CROSS_STORE_ACTION,
                "target_type": target_type,
                "target_id": target_uuid,
                "metadata": Jsonb(metadata),
                "correlation_id": correlation_uuid,
            },
        )
        session.commit()
    except Exception:
        session.rollback()
        logger.warning(
            "failed to write cross-store security audit", exc_info=False
        )
    finally:
        session.close()
