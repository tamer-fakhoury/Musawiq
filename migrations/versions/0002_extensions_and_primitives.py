"""DB-0.2 — extensions and shared primitives.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25

Installs the citext and pg_trgm extensions and creates the shared trigger
functions fn_touch_updated_at() and fn_block_mutation() in the public schema.
No tables are created. Downgrade drops both functions and intentionally leaves
the extensions installed for later revisions.
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.fn_touch_updated_at()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.updated_at := now();
            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.fn_block_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'append-only table %: % is not allowed', TG_TABLE_NAME, TG_OP;
            RETURN OLD;
        END;
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.fn_block_mutation()")
    op.execute("DROP FUNCTION IF EXISTS public.fn_touch_updated_at()")
