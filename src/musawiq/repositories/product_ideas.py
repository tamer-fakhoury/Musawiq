"""Tenant-scoped product idea library."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.repositories.base import TenantScopedRepository


class ProductIdeaRepository(TenantScopedRepository):
    """Repository for ``product_ideas`` rows."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, "product_ideas")

    def insert_idea(self, values: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.insert(values)

    def get_idea(
        self, idea_id: uuid.UUID | str
    ) -> Mapping[str, Any] | None:
        return self.get(idea_id)

    def update_idea(
        self, idea_id: uuid.UUID | str, values: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        return self.update(idea_id, values)

    def list_ideas(
        self,
        *,
        state: str | None = None,
        category_id: uuid.UUID | None = None,
        niche_id: uuid.UUID | None = None,
        generation_run_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Mapping[str, Any]]:
        tenant = self._tenant()
        clauses = ["store_id = :store_id"]
        params: dict[str, Any] = {
            "store_id": tenant.store_id,
            "limit": limit,
            "offset": offset,
        }
        if state is not None:
            clauses.append("state = :state")
            params["state"] = state
        if category_id is not None:
            clauses.append("category_id = :category_id")
            params["category_id"] = category_id
        if niche_id is not None:
            clauses.append("niche_id = :niche_id")
            params["niche_id"] = niche_id
        if generation_run_id is not None:
            clauses.append("generation_run_id = :generation_run_id")
            params["generation_run_id"] = generation_run_id
        return list(
            self.session.execute(
                text(
                    f"""
                    SELECT * FROM public.product_ideas
                    WHERE {' AND '.join(clauses)}
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
            .mappings()
            .all()
        )

    def dedupe_rows(self) -> list[Mapping[str, Any]]:
        tenant = self._tenant()
        return list(
            self.session.execute(
                text(
                    """
                    SELECT name, description FROM public.product_ideas
                    WHERE store_id = :store_id AND state = 'dismissed'
                    """
                ),
                {"store_id": tenant.store_id},
            )
            .mappings()
            .all()
        )


__all__ = ["ProductIdeaRepository"]
