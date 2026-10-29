"""Tenant-scoped evaluation persistence."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.repositories.base import TenantScopedRepository


class EvaluationRepository(TenantScopedRepository):
    """Repository for immutable ``evaluations`` rows."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, "evaluations")

    def insert_evaluation(self, values: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.insert(values)

    def find_idempotent(
        self,
        concept_id: uuid.UUID | str,
        scoring_model_id: uuid.UUID | str,
        model_version: int,
        input_snapshot: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        tenant = self._tenant()
        snapshot = json.dumps(
            input_snapshot, sort_keys=True, separators=(",", ":")
        )
        return (
            self.session.execute(
                text(
                    """
                    SELECT * FROM public.evaluations
                    WHERE store_id = :store_id
                      AND product_concept_id = :concept_id
                      AND scoring_model_id = :model_id
                      AND model_version = :model_version
                      AND input_snapshot = CAST(:snapshot AS jsonb)
                    ORDER BY evaluated_at DESC, created_at DESC, id DESC
                    LIMIT 1
                    """
                ),
                {
                    "store_id": tenant.store_id,
                    "concept_id": uuid.UUID(str(concept_id)),
                    "model_id": uuid.UUID(str(scoring_model_id)),
                    "model_version": model_version,
                    "snapshot": snapshot,
                },
            )
            .mappings()
            .one_or_none()
        )

    def get(self, evaluation_id: uuid.UUID | str) -> Mapping[str, Any] | None:
        return super().get(evaluation_id)

    def latest_for_concept(
        self, concept_id: uuid.UUID | str
    ) -> Mapping[str, Any] | None:
        tenant = self._tenant()
        return (
            self.session.execute(
                text(
                    """
                    SELECT * FROM public.evaluations
                    WHERE store_id = :store_id
                      AND product_concept_id = :concept_id
                    ORDER BY evaluated_at DESC, created_at DESC, id DESC
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


__all__ = ["EvaluationRepository"]
