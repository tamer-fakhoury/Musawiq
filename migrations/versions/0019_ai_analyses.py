"""FR-8.4 - AI analyses.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-26

Stores each demand/issue analysis produced by the AI feedback loop. The table is
tenant-owned, so forced RLS is attached in the same revision.
"""

from __future__ import annotations

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ai_analyses (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            campaign_id uuid NOT NULL,
            parent_analysis_id uuid,
            window_start timestamptz,
            window_end timestamptz,
            status text NOT NULL,
            provider text,
            model_version text,
            prompt_version text,
            input_snapshot jsonb NOT NULL,
            result jsonb,
            demand_level text,
            confidence numeric(5,4),
            created_by uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_ai_analyses_status CHECK (
                status IN ('succeeded', 'degraded', 'failed')
            ),
            CONSTRAINT fk_ai_analyses_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_ai_analyses_campaign_id FOREIGN KEY (campaign_id)
                REFERENCES campaigns (id),
            CONSTRAINT fk_ai_analyses_parent_analysis_id FOREIGN KEY (parent_analysis_id)
                REFERENCES ai_analyses (id),
            CONSTRAINT fk_ai_analyses_created_by FOREIGN KEY (created_by)
                REFERENCES users (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_ai_analyses_campaign_id_created_at
        ON ai_analyses (campaign_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_ai_analyses_parent_analysis_id
        ON ai_analyses (parent_analysis_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_ai_analyses_store_id
        ON ai_analyses (store_id)
        """
    )
    op.execute(
        """
        ALTER TABLE ai_analyses ENABLE ROW LEVEL SECURITY;
        ALTER TABLE ai_analyses FORCE ROW LEVEL SECURITY;
        CREATE POLICY p_ai_analyses_tenant ON ai_analyses FOR ALL
            USING (
                store_id = nullif(current_setting('app.store_id', true), '')::uuid
            )
            WITH CHECK (
                store_id = nullif(current_setting('app.store_id', true), '')::uuid
            );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP POLICY IF EXISTS p_ai_analyses_tenant ON ai_analyses;
        ALTER TABLE ai_analyses NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE ai_analyses DISABLE ROW LEVEL SECURITY;
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_ai_analyses_store_id")
    op.execute("DROP INDEX IF EXISTS ix_ai_analyses_parent_analysis_id")
    op.execute("DROP INDEX IF EXISTS ix_ai_analyses_campaign_id_created_at")
    op.execute("DROP TABLE IF EXISTS ai_analyses")
