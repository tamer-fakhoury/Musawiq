"""Worker heartbeat storage for the background job runtime."""

from __future__ import annotations

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE worker_heartbeats (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            worker_name text NOT NULL UNIQUE,
            status text NOT NULL DEFAULT 'running',
            processed_jobs integer NOT NULL DEFAULT 0,
            failed_jobs integer NOT NULL DEFAULT 0,
            started_at timestamptz NOT NULL DEFAULT now(),
            last_heartbeat_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_worker_heartbeats_status CHECK (
                status IN ('running', 'stopping', 'stopped')
            )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY p_async_jobs_system_update ON async_jobs
            FOR UPDATE
            USING (store_id IS NULL)
            WITH CHECK (store_id IS NULL)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS p_async_jobs_system_update ON async_jobs")
    op.execute("DROP TABLE IF EXISTS worker_heartbeats")
