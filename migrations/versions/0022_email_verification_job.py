"""Allow email verification jobs and system job inserts (FR-0.6.1).

Signup queues a verification email before the user owns a store; the async job
therefore has ``store_id = NULL``. These jobs are system jobs, so the runtime
role may insert rows with a null store while tenant jobs stay scoped.
"""

from __future__ import annotations

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE async_jobs DROP CONSTRAINT ck_async_jobs_job_type"
    )
    op.execute(
        """
        ALTER TABLE async_jobs
        ADD CONSTRAINT ck_async_jobs_job_type CHECK (
            job_type IN (
                'import',
                'integration_sync',
                'page_generation',
                'ad_publication',
                'metric_sync',
                'recommendation_generation',
                'content_generation',
                'email_verification'
            )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY p_async_jobs_system_insert ON async_jobs
            FOR INSERT
            WITH CHECK (store_id IS NULL)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS p_async_jobs_system_insert ON async_jobs")
    op.execute(
        "ALTER TABLE async_jobs DROP CONSTRAINT ck_async_jobs_job_type"
    )
    op.execute(
        """
        ALTER TABLE async_jobs
        ADD CONSTRAINT ck_async_jobs_job_type CHECK (
            job_type IN (
                'import',
                'integration_sync',
                'page_generation',
                'ad_publication',
                'metric_sync',
                'recommendation_generation',
                'content_generation'
            )
        )
        """
    )
