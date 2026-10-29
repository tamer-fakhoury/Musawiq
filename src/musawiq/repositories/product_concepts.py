"""Tenant-scoped product concept repository."""

from __future__ import annotations

from sqlalchemy.orm import Session

from musawiq.repositories.base import TenantScopedRepository


class ProductConceptRepository(TenantScopedRepository):
    """Repository for the ``product_concepts`` aggregate."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, "product_concepts")


__all__ = ["ProductConceptRepository"]
