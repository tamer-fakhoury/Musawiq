"""DB-0.14b - indexes for the three order FKs added in DB-0.13.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-25

DB-0.13 introduced orders.campaign_id, orders.landing_page_id and
orders.post_id. The schema audit requires a leading index on every required
foreign-key column, so this revision adds the three that were missing.
"""

from __future__ import annotations

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

INDEXES = [
    ("ix_orders_campaign_id", "orders", "campaign_id"),
    ("ix_orders_landing_page_id", "orders", "landing_page_id"),
    ("ix_orders_post_id", "orders", "post_id"),
]


def upgrade() -> None:
    for name, table, column in INDEXES:
        op.execute(f"CREATE INDEX {name} ON {table} ({column})")


def downgrade() -> None:
    for name, _table, _column in reversed(INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {name}")
