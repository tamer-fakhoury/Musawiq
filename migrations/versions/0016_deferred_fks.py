"""DB-0.13 - close deferred order foreign keys.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-25

Adds the three deferred order FKs listed in docs/FK-MATRIX.md. No tables,
columns, indexes, or manifest entries change. Downgrade drops the three
constraints.
"""

from __future__ import annotations

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE orders
        ADD CONSTRAINT fk_orders_campaign_id FOREIGN KEY (campaign_id)
        REFERENCES campaigns (id)
        """
    )
    op.execute(
        """
        ALTER TABLE orders
        ADD CONSTRAINT fk_orders_landing_page_id FOREIGN KEY (landing_page_id)
        REFERENCES landing_pages (id)
        """
    )
    op.execute(
        """
        ALTER TABLE orders
        ADD CONSTRAINT fk_orders_post_id FOREIGN KEY (post_id)
        REFERENCES posts (id)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS fk_orders_post_id")
    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS fk_orders_landing_page_id")
    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS fk_orders_campaign_id")
