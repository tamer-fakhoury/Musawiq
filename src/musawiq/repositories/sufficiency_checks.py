"""Tenant-scoped sufficiency check persistence."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.repositories.base import TenantScopedRepository


class SufficiencyCheckRepository(TenantScopedRepository):
    """Repository for ``sufficiency_checks`` rows."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, "sufficiency_checks")

    def insert_check(self, values: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.insert(values)

    def get_check(
        self, check_id: uuid.UUID | str
    ) -> Mapping[str, Any] | None:
        return self.get(check_id)

    def latest_for_concept(
        self, concept_id: uuid.UUID | str
    ) -> Mapping[str, Any] | None:
        tenant = self._tenant()
        return (
            self.session.execute(
                text(
                    """
                    SELECT * FROM public.sufficiency_checks
                    WHERE store_id = :store_id
                      AND product_concept_id = :concept_id
                    ORDER BY checked_at DESC, created_at DESC, id DESC
                    LIMIT 1
                    """
                ),
                {
                    "store_id": tenant.store_id,
                    "concept_id": uuid.UUID(str(concept_id)),
                },
            )
            .mappings()
            .one_or_none()
        )


__all__ = ["SufficiencyCheckRepository"]
