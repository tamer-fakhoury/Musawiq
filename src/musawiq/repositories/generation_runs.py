"""Tenant-scoped recommendation generation runs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.repositories.base import TenantScopedRepository


class GenerationRunRepository(TenantScopedRepository):
    """Repository for ``generation_runs`` rows."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, "generation_runs")

    def get_for_update(
        self, run_id: object
    ) -> Mapping[str, Any] | None:
        tenant = self._tenant()
        return (
            self.session.execute(
                text(
                    """
                    SELECT * FROM public.generation_runs
                    WHERE id = :id AND store_id = :store_id
                    FOR UPDATE
                    """
                ),
                {"id": run_id, "store_id": tenant.store_id},
            )
            .mappings()
            .one_or_none()
        )

    def insert_run(self, values: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.insert(values)

    def update_run(
        self, run_id: object, values: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        return self.update(run_id, values)

    def list_runs(
        self, *, limit: int = 50, offset: int = 0
    ) -> list[Mapping[str, Any]]:
        tenant = self._tenant()
        return list(
            self.session.execute(
                text(
                    """
                    SELECT * FROM public.generation_runs
                    WHERE store_id = :store_id
                    ORDER BY created_at DESC, id DESC
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


__all__ = ["GenerationRunRepository"]
