"""DB-0.7 - product evaluation tables.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-25

Creates product concepts, scoring models, sufficiency checks, evaluations, and
append-only score factors. The product_concepts.source_idea_id FK stays
deferred until product_ideas exists. Downgrade drops the tables in reverse
order.
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE product_concepts (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            source_idea_id uuid,
            name text NOT NULL,
            description text,
            category_id uuid NOT NULL,
            niche_id uuid,
            price_minor bigint NOT NULL,
            cost_minor bigint NOT NULL,
            currency char(3) NOT NULL,
            gross_margin_bp integer NOT NULL,
            image_file_id uuid,
            status text NOT NULL DEFAULT 'draft',
            version integer NOT NULL DEFAULT 1,
            created_by uuid NOT NULL,
            deleted_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_product_concepts_status CHECK (
                status IN ('draft', 'evaluated', 'selected', 'archived')
            ),
            CONSTRAINT fk_product_concepts_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_product_concepts_category_id FOREIGN KEY (category_id)
                REFERENCES categories (id),
            CONSTRAINT fk_product_concepts_niche_id FOREIGN KEY (niche_id)
                REFERENCES niches (id),
            CONSTRAINT fk_product_concepts_currency FOREIGN KEY (currency)
                REFERENCES currencies (code),
            CONSTRAINT fk_product_concepts_image_file_id FOREIGN KEY (image_file_id)
                REFERENCES stored_files (id),
            CONSTRAINT fk_product_concepts_created_by FOREIGN KEY (created_by)
                REFERENCES users (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE scoring_models (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid,
            key text NOT NULL,
            version integer NOT NULL,
            name text NOT NULL,
            description text,
            weights jsonb NOT NULL,
            parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
            is_active boolean NOT NULL DEFAULT true,
            effective_from timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_scoring_models_key_version UNIQUE (key, version),
            CONSTRAINT fk_scoring_models_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE sufficiency_checks (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            product_concept_id uuid NOT NULL,
            sales_history_status text NOT NULL,
            audience_status text NOT NULL,
            cost_price_status text NOT NULL,
            competitive_data_status text NOT NULL,
            overall_status text NOT NULL,
            blocking_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
            checked_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_sufficiency_checks_sales_history_status CHECK (
                sales_history_status IN ('available', 'missing', 'stale', 'insufficient')
            ),
            CONSTRAINT ck_sufficiency_checks_audience_status CHECK (
                audience_status IN ('available', 'missing', 'stale', 'insufficient')
            ),
            CONSTRAINT ck_sufficiency_checks_cost_price_status CHECK (
                cost_price_status IN ('available', 'missing', 'stale', 'insufficient')
            ),
            CONSTRAINT ck_sufficiency_checks_competitive_data_status CHECK (
                competitive_data_status IN ('available', 'missing', 'stale', 'insufficient')
            ),
            CONSTRAINT ck_sufficiency_checks_overall_status CHECK (
                overall_status IN ('sufficient', 'insufficient')
            ),
            CONSTRAINT fk_sufficiency_checks_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_sufficiency_checks_product_concept_id FOREIGN KEY (product_concept_id)
                REFERENCES product_concepts (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE evaluations (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            product_concept_id uuid NOT NULL,
            scoring_model_id uuid NOT NULL,
            model_version integer NOT NULL,
            score numeric(7,4),
            score_scale smallint NOT NULL DEFAULT 100,
            confidence text NOT NULL,
            is_reliable boolean NOT NULL,
            sufficiency_check_id uuid,
            input_snapshot jsonb NOT NULL,
            evaluated_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_evaluations_confidence CHECK (
                confidence IN ('high', 'medium', 'low')
            ),
            CONSTRAINT fk_evaluations_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_evaluations_product_concept_id FOREIGN KEY (product_concept_id)
                REFERENCES product_concepts (id),
            CONSTRAINT fk_evaluations_scoring_model_id FOREIGN KEY (scoring_model_id)
                REFERENCES scoring_models (id),
            CONSTRAINT fk_evaluations_sufficiency_check_id FOREIGN KEY (sufficiency_check_id)
                REFERENCES sufficiency_checks (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE score_factors (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            evaluation_id uuid NOT NULL,
            factor_key text NOT NULL,
            factor_label text NOT NULL,
            direction text NOT NULL,
            contribution numeric(7,4) NOT NULL,
            explanation text NOT NULL,
            evidence jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_score_factors_direction CHECK (
                direction IN ('positive', 'negative', 'neutral')
            ),
            CONSTRAINT fk_score_factors_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_score_factors_evaluation_id FOREIGN KEY (evaluation_id)
                REFERENCES evaluations (id)
        )
        """
    )

    op.execute(
        """
        CREATE INDEX ix_product_concepts_store_id_status
        ON product_concepts (store_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_sufficiency_checks_product_concept_id_checked_at
        ON sufficiency_checks (product_concept_id, checked_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_evaluations_product_concept_id_evaluated_at
        ON evaluations (product_concept_id, evaluated_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_score_factors_evaluation_id
        ON score_factors (evaluation_id)
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_product_concepts_touch_updated_at
        BEFORE UPDATE ON product_concepts
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_scoring_models_touch_updated_at
        BEFORE UPDATE ON scoring_models
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_score_factors_block_mutation
        BEFORE UPDATE OR DELETE ON score_factors
        FOR EACH ROW EXECUTE FUNCTION fn_block_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS score_factors")
    op.execute("DROP TABLE IF EXISTS evaluations")
    op.execute("DROP TABLE IF EXISTS sufficiency_checks")
    op.execute("DROP TABLE IF EXISTS scoring_models")
    op.execute("DROP TABLE IF EXISTS product_concepts")
