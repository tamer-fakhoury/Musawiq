"""Tenant-scoped order history reads for sufficiency assessment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.repositories.base import TenantScopedRepository


@dataclass(frozen=True, slots=True)
class SalesHistorySummary:
    """Aggregate sales-history facts used by the sufficiency policy."""

    order_count: int
    first_placed_at: datetime | None
    last_placed_at: datetime | None


class OrderRepository(TenantScopedRepository):
    """Repository for order-level history queries."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, "orders")

    def sales_history(self) -> SalesHistorySummary:
        tenant = self._tenant()
        row = self.session.execute(
            text(
                """
                SELECT count(*) AS order_count,
                       min(placed_at) AS first_placed_at,
                       max(placed_at) AS last_placed_at
                FROM public.orders
                WHERE store_id = :store_id
                  AND status IN ('confirmed', 'fulfilled')
                """
            ),
            {"store_id": tenant.store_id},
        ).mappings().one()
        return SalesHistorySummary(
            order_count=int(row["order_count"]),
            first_placed_at=row["first_placed_at"],
            last_placed_at=row["last_placed_at"],
        )


__all__ = ["OrderRepository", "SalesHistorySummary"]
