"""Tenant-visible scoring model registry reads and writes."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class ScoringModelRepository:
    """Repository for platform-default and store-specific scoring models."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_visible(
        self, model_id: uuid.UUID | str, store_id: uuid.UUID
    ) -> Mapping[str, Any] | None:
        return (
            self.session.execute(
                text(
                    """
                    SELECT * FROM public.scoring_models
                    WHERE id = :id
                      AND is_active
                      AND effective_from <= now()
                      AND (store_id = :store_id OR store_id IS NULL)
                    LIMIT 1
                    """
                ),
                {"id": uuid.UUID(str(model_id)), "store_id": store_id},
            )
            .mappings()
            .one_or_none()
        )

    def active_for_store(
        self, store_id: uuid.UUID
    ) -> Mapping[str, Any] | None:
        return (
            self.session.execute(
                text(
                    """
                    SELECT * FROM public.scoring_models
                    WHERE store_id = :store_id
                      AND is_active
                      AND effective_from <= now()
                    ORDER BY effective_from DESC, version DESC, id DESC
                    LIMIT 1
                    """
                ),
                {"store_id": store_id},
            )
            .mappings()
            .one_or_none()
        )

    def platform_default(self) -> Mapping[str, Any] | None:
        return (
            self.session.execute(
                text(
                    """
                    SELECT * FROM public.scoring_models
                    WHERE store_id IS NULL
                      AND is_active
                      AND effective_from <= now()
                    ORDER BY effective_from DESC, version DESC, id DESC
                    LIMIT 1
                    """
                )
            )
            .mappings()
            .one_or_none()
        )

    def get_by_key_version(
        self, key: str, version: int
    ) -> Mapping[str, Any] | None:
        return (
            self.session.execute(
                text(
                    """
                    SELECT * FROM public.scoring_models
                    WHERE key = :key AND version = :version
                    LIMIT 1
                    """
                ),
                {"key": key, "version": version},
            )
            .mappings()
            .one_or_none()
        )

    def insert(self, values: Mapping[str, Any]) -> Mapping[str, Any]:
        columns = list(values)
        placeholders = [f":value_{index}" for index in range(len(columns))]
        params = {
            f"value_{index}": value
            for index, value in enumerate(values.values())
        }
        sql = (
            "INSERT INTO public.scoring_models "
            f"({', '.join(columns)}) "
            f"VALUES ({', '.join(placeholders)}) RETURNING *"
        )
        return self.session.execute(text(sql), params).mappings().one()

    def list_visible(self, store_id: uuid.UUID) -> list[Mapping[str, Any]]:
        return list(
            self.session.execute(
                text(
                    """
                    SELECT * FROM public.scoring_models
                    WHERE store_id = :store_id OR store_id IS NULL
                    ORDER BY store_id NULLS LAST, effective_from DESC,
                             version DESC, id DESC
                    """
                ),
                {"store_id": store_id},
            )
            .mappings()
            .all()
        )


__all__ = ["ScoringModelRepository"]
