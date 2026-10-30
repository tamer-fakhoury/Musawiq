"""Tenant-scoped evidence attached to product ideas."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.repositories.base import TenantScopedRepository


class IdeaEvidenceRepository(TenantScopedRepository):
    """Repository for ``idea_evidences`` rows."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, "idea_evidences")

    def insert_evidence(self, values: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.insert(values)

    def list_for_idea(
        self, idea_id: uuid.UUID | str
    ) -> list[Mapping[str, Any]]:
        tenant = self._tenant()
        return list(
            self.session.execute(
                text(
                    """
                    SELECT * FROM public.idea_evidences
                    WHERE store_id = :store_id
                      AND product_idea_id = :idea_id
                    ORDER BY created_at, id
                    """
                ),
                {
                    "store_id": tenant.store_id,
                    "idea_id": uuid.UUID(str(idea_id)),
                },
            )
            .mappings()
            .all()
        )

    def list_for_ideas(
        self, idea_ids: list[uuid.UUID]
    ) -> list[Mapping[str, Any]]:
        if not idea_ids:
            return []
        tenant = self._tenant()
        return list(
            self.session.execute(
                text(
                    """
                    SELECT * FROM public.idea_evidences
                    WHERE store_id = :store_id
                      AND product_idea_id = ANY(CAST(:idea_ids AS uuid[]))
                    ORDER BY created_at, id
                    """
                ),
                {
                    "store_id": tenant.store_id,
                    "idea_ids": idea_ids,
                },
            )
            .mappings()
            .all()
        )


__all__ = ["IdeaEvidenceRepository"]
