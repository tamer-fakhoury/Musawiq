"""Tenant-scoped score factor persistence."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.repositories.base import TenantScopedRepository


class ScoreFactorRepository(TenantScopedRepository):
    """Repository for append-only ``score_factors`` rows."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, "score_factors")

    def insert_factor(self, values: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.insert(values)

    def list_for_evaluation(
        self, evaluation_id: uuid.UUID | str
    ) -> list[Mapping[str, Any]]:
        tenant = self._tenant()
        return list(
            self.session.execute(
                text(
                    """
                    SELECT * FROM public.score_factors
                    WHERE store_id = :store_id
                      AND evaluation_id = :evaluation_id
                    ORDER BY abs(contribution) DESC, factor_key, id
                    """
                ),
                {
                    "store_id": tenant.store_id,
                    "evaluation_id": uuid.UUID(str(evaluation_id)),
                },
            )
            .mappings()
            .all()
        )


__all__ = ["ScoreFactorRepository"]
