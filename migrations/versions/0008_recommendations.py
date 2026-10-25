"""DB-0.8 - recommendation tables.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-25

Creates generation runs, product ideas, and idea evidence, then closes the
circular reference by adding product_concepts.source_idea_id -> product_ideas.
Downgrade removes the product_concepts FK first, then drops the tables in
reverse order.
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE generation_runs (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            requested_by uuid NOT NULL,
            model_version text NOT NULL,
            input_snapshot jsonb NOT NULL,
            requested_count integer NOT NULL,
            returned_count integer NOT NULL DEFAULT 0,
            status text NOT NULL,
            error_message text,
            started_at timestamptz,
            finished_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_generation_runs_requested_count CHECK (requested_count > 0),
            CONSTRAINT ck_generation_runs_returned_count CHECK (returned_count >= 0),
            CONSTRAINT ck_generation_runs_status CHECK (
                status IN ('queued', 'running', 'succeeded', 'failed')
            ),
            CONSTRAINT fk_generation_runs_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_generation_runs_requested_by FOREIGN KEY (requested_by)
                REFERENCES users (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE product_ideas (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            generation_run_id uuid NOT NULL,
            name text NOT NULL,
            description text NOT NULL,
            category_id uuid,
            niche_id uuid,
            rationale text NOT NULL,
            state text NOT NULL DEFAULT 'new',
            dismissed_reason text,
            converted_concept_id uuid,
            model_version text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_product_ideas_state CHECK (
                state IN ('new', 'saved', 'dismissed', 'converted')
            ),
            CONSTRAINT fk_product_ideas_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_product_ideas_generation_run_id FOREIGN KEY (generation_run_id)
                REFERENCES generation_runs (id),
            CONSTRAINT fk_product_ideas_category_id FOREIGN KEY (category_id)
                REFERENCES categories (id),
            CONSTRAINT fk_product_ideas_niche_id FOREIGN KEY (niche_id)
                REFERENCES niches (id),
            CONSTRAINT fk_product_ideas_converted_concept_id FOREIGN KEY (converted_concept_id)
                REFERENCES product_concepts (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE idea_evidences (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            product_idea_id uuid NOT NULL,
            evidence_type text NOT NULL,
            claim text NOT NULL,
            source_name text,
            source_url text,
            source_published_at timestamptz,
            retrieved_at timestamptz,
            confidence numeric(5,4),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_idea_evidences_evidence_type CHECK (
                evidence_type IN ('verified', 'hypothesis')
            ),
            CONSTRAINT ck_idea_evidences_verified_source_url CHECK (
                evidence_type = 'hypothesis' OR source_url IS NOT NULL
            ),
            CONSTRAINT fk_idea_evidences_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_idea_evidences_product_idea_id FOREIGN KEY (product_idea_id)
                REFERENCES product_ideas (id)
        )
        """
    )

    op.execute(
        """
        CREATE INDEX ix_product_ideas_store_id_state
        ON product_ideas (store_id, state)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_idea_evidences_product_idea_id
        ON idea_evidences (product_idea_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_product_ideas_generation_run_id
        ON product_ideas (generation_run_id)
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_product_ideas_touch_updated_at
        BEFORE UPDATE ON product_ideas
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )

    op.execute(
        """
        ALTER TABLE product_concepts
        ADD CONSTRAINT fk_product_concepts_source_idea_id FOREIGN KEY (source_idea_id)
        REFERENCES product_ideas (id)
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE product_concepts DROP CONSTRAINT IF EXISTS fk_product_concepts_source_idea_id"
    )
    op.execute("DROP TABLE IF EXISTS idea_evidences")
    op.execute("DROP TABLE IF EXISTS product_ideas")
    op.execute("DROP TABLE IF EXISTS generation_runs")
