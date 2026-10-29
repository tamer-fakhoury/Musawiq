"""Tenant-scoped product concept repository."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.repositories.base import TenantScopedRepository

_SORT_SQL = {
    "score": "latest.score",
    "category": "category.name",
    "created_at": "concept.created_at",
}


class ProductConceptRepository(TenantScopedRepository):
    """Repository for the ``product_concepts`` aggregate."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, "product_concepts")

    def list_filtered(
        self,
        *,
        status: str | None = None,
        category_id: uuid.UUID | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        search: str | None = None,
        sort: str = "created_at",
        direction: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> list[Mapping[str, Any]]:
        tenant = self._tenant()
        if sort not in _SORT_SQL:
            raise ValueError("unsupported concept sort key")
        if direction not in {"asc", "desc"}:
            raise ValueError("direction must be asc or desc")
        if not isinstance(limit, int) or limit < 1 or limit > 1000:
            raise ValueError("limit must be an integer between 1 and 1000")
        if not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a non-negative integer")

        clauses = [
            "concept.store_id = :tenant_store_id",
            "concept.deleted_at IS NULL",
        ]
        params: dict[str, Any] = {
            "tenant_store_id": tenant.store_id,
            "limit": limit,
            "offset": offset,
        }
        if status is not None:
            clauses.append("concept.status = :status")
            params["status"] = status
        if category_id is not None:
            clauses.append("concept.category_id = :category_id")
            params["category_id"] = category_id
        if created_from is not None:
            clauses.append("concept.created_at >= :created_from")
            params["created_from"] = created_from
        if created_to is not None:
            clauses.append("concept.created_at <= :created_to")
            params["created_to"] = created_to
        if search:
            clauses.append(
                "(concept.name ILIKE :search "
                "OR coalesce(concept.description, '') ILIKE :search)"
            )
            params["search"] = f"%{search}%"

        if sort == "score":
            order_by = (
                f"latest.score {direction} NULLS LAST, "
                f"concept.created_at {direction}, concept.id {direction}"
            )
        elif sort == "category":
            order_by = (
                f"category.name {direction} NULLS LAST, "
                f"concept.created_at DESC, concept.id DESC"
            )
        else:
            order_by = f"concept.created_at {direction}, concept.id {direction}"

        sql = f"""
            SELECT concept.*,
                   latest.id AS latest_evaluation_id,
                   latest.score AS latest_score,
                   latest.score_scale AS latest_score_scale,
                   latest.confidence AS latest_confidence,
                   latest.is_reliable AS latest_is_reliable,
                   latest.evaluated_at AS latest_evaluated_at
            FROM {self._table_sql} AS concept
            LEFT JOIN public.categories AS category
              ON category.id = concept.category_id
            LEFT JOIN LATERAL (
                SELECT evaluation.id,
                       evaluation.score,
                       evaluation.score_scale,
                       evaluation.confidence,
                       evaluation.is_reliable,
                       evaluation.evaluated_at
                FROM public.evaluations AS evaluation
                WHERE evaluation.store_id = concept.store_id
                  AND evaluation.product_concept_id = concept.id
                ORDER BY evaluation.evaluated_at DESC,
                         evaluation.created_at DESC,
                         evaluation.id DESC
                LIMIT 1
            ) AS latest ON true
            WHERE {' AND '.join(clauses)}
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
        """
        return list(
            self.session.execute(text(sql), params).mappings().all()
        )

    def get_with_latest(
        self, record_id: uuid.UUID | str
    ) -> Mapping[str, Any] | None:
        tenant = self._tenant()
        concept_uuid = uuid.UUID(str(record_id))
        sql = f"""
            SELECT concept.*,
                   latest.id AS latest_evaluation_id,
                   latest.score AS latest_score,
                   latest.score_scale AS latest_score_scale,
                   latest.confidence AS latest_confidence,
                   latest.is_reliable AS latest_is_reliable,
                   latest.evaluated_at AS latest_evaluated_at
            FROM {self._table_sql} AS concept
            LEFT JOIN LATERAL (
                SELECT evaluation.id,
                       evaluation.score,
                       evaluation.score_scale,
                       evaluation.confidence,
                       evaluation.is_reliable,
                       evaluation.evaluated_at
                FROM public.evaluations AS evaluation
                WHERE evaluation.store_id = concept.store_id
                  AND evaluation.product_concept_id = concept.id
                ORDER BY evaluation.evaluated_at DESC,
                         evaluation.created_at DESC,
                         evaluation.id DESC
                LIMIT 1
            ) AS latest ON true
            WHERE concept.id = :id
              AND concept.store_id = :tenant_store_id
            LIMIT 1
        """
        return (
            self.session.execute(
                text(sql),
                {
                    "id": concept_uuid,
                    "tenant_store_id": tenant.store_id,
                },
            )
            .mappings()
            .one_or_none()
        )

    def has_evaluation(self, record_id: uuid.UUID | str) -> bool:
        tenant = self._tenant()
        concept_uuid = uuid.UUID(str(record_id))
        row = self.session.execute(
            text(
                """
                SELECT 1 FROM public.evaluations
                WHERE store_id = :tenant_store_id
                  AND product_concept_id = :id
                LIMIT 1
                """
            ),
            {"id": concept_uuid, "tenant_store_id": tenant.store_id},
        ).first()
        return row is not None

    def update_versioned(
        self,
        record_id: uuid.UUID | str,
        expected_version: int,
        values: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        tenant = self._tenant()
        if not isinstance(expected_version, int) or expected_version < 1:
            raise ValueError("expected_version must be a positive integer")
        if not values:
            raise ValueError("update requires at least one column value")
        if "store_id" in values:
            raise ValueError("update cannot change store_id")
        if "id" in values:
            raise ValueError("update cannot change id")

        concept_uuid = uuid.UUID(str(record_id))
        assignments: list[str] = []
        params: dict[str, Any] = {}
        for index, (column, value) in enumerate(values.items()):
            if column not in {
                "name",
                "description",
                "category_id",
                "niche_id",
                "price_minor",
                "cost_minor",
                "currency",
                "gross_margin_bp",
                "image_file_id",
                "status",
                "version",
            }:
                raise ValueError(f"unsupported concept column {column!r}")
            assignments.append(f'"{column}" = :set_{index}')
            params[f"set_{index}"] = value

        params.update(
            {
                "id": concept_uuid,
                "tenant_store_id": tenant.store_id,
                "expected_version": expected_version,
            }
        )
        sql = f"""
            UPDATE {self._table_sql}
            SET {', '.join(assignments)}
            WHERE id = :id
              AND store_id = :tenant_store_id
              AND version = :expected_version
              AND deleted_at IS NULL
            RETURNING *
        """
        return (
            self.session.execute(text(sql), params).mappings().one_or_none()
        )


__all__ = ["ProductConceptRepository"]
