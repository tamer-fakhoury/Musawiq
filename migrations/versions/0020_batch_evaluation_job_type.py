"""Allow batch viability evaluation jobs.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-29
"""

from __future__ import annotations

from alembic import op

revision = "0020"
down_revision = "0019"
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
                'batch_evaluation'
            )
        )
        """
    )


def downgrade() -> None:
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
