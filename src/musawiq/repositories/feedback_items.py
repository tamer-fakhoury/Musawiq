"""Tenant-scoped customer feedback persistence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.repositories.base import TenantScopedRepository


class FeedbackItemRepository(TenantScopedRepository):
    """Repository for ``feedback_items`` rows."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, "feedback_items")

    def insert_item(self, values: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.insert(values)

    def list_items(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[Mapping[str, Any]]:
        tenant = self._tenant()
        return list(
            self.session.execute(
                text(
                    """
                    SELECT * FROM public.feedback_items
                    WHERE store_id = :store_id
                    ORDER BY captured_at DESC, created_at DESC, id DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {
                    "store_id": tenant.store_id,
                    "limit": limit,
                    "offset": offset,
                },
            )
            .mappings()
            .all()
        )

    def count_items(self) -> int:
        tenant = self._tenant()
        return int(
            self.session.execute(
                text(
                    """
                    SELECT count(*) FROM public.feedback_items
                    WHERE store_id = :store_id
                    """
                ),
                {"store_id": tenant.store_id},
            ).scalar_one()
        )


__all__ = ["FeedbackItemRepository"]
