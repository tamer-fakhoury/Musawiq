"""DB-0.12 - decision and investment tables.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-25

Creates decision rule sets, append-only test-result snapshots and verdicts,
versioned investment profiles and recommendations, and their demand, unit
economics, and quantity-scenario children. Downgrade drops the tables in
reverse order.
"""

from __future__ import annotations

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE decision_rule_sets (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid,
            category_id uuid,
            version integer NOT NULL,
            is_active boolean NOT NULL DEFAULT true,
            min_spend_minor bigint NOT NULL DEFAULT 0,
            min_clicks integer NOT NULL DEFAULT 0,
            min_conversions integer NOT NULL DEFAULT 0,
            min_confirmed_deposits integer NOT NULL DEFAULT 0,
            min_conversion_rate numeric(9,6),
            max_cost_per_conversion_minor bigint,
            rules jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_by uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_decision_rule_sets_natural_key UNIQUE NULLS NOT DISTINCT (
                store_id,
                category_id,
                version
            ),
            CONSTRAINT fk_decision_rule_sets_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_decision_rule_sets_category_id FOREIGN KEY (category_id)
                REFERENCES categories (id),
            CONSTRAINT fk_decision_rule_sets_created_by FOREIGN KEY (created_by)
                REFERENCES users (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE test_result_snapshots (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            test_id uuid NOT NULL,
            period_start timestamptz NOT NULL,
            period_end timestamptz NOT NULL,
            currency char(3) NOT NULL,
            spend_minor bigint NOT NULL,
            impressions bigint NOT NULL,
            clicks bigint NOT NULL,
            tracked_conversions bigint NOT NULL,
            confirmed_deposits bigint NOT NULL,
            conversion_rate numeric(9,6),
            cost_per_conversion_minor bigint,
            data_completeness numeric(5,4) NOT NULL,
            source_metric_snapshot_ids uuid[] NOT NULL DEFAULT '{}',
            captured_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_test_result_snapshots_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_test_result_snapshots_test_id FOREIGN KEY (test_id)
                REFERENCES tests (id),
            CONSTRAINT fk_test_result_snapshots_currency FOREIGN KEY (currency)
                REFERENCES currencies (code)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_test_result_snapshots_test_id_captured_at
        ON test_result_snapshots (test_id, captured_at DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE verdicts (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            test_id uuid NOT NULL,
            result_snapshot_id uuid NOT NULL,
            decision_rule_set_id uuid NOT NULL,
            outcome text NOT NULL,
            is_conclusive boolean NOT NULL,
            primary_reason text NOT NULL,
            limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
            rule_trace jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_verdicts_outcome CHECK (
                outcome IN ('go', 'no_go', 'extend_test')
            ),
            CONSTRAINT fk_verdicts_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_verdicts_test_id FOREIGN KEY (test_id)
                REFERENCES tests (id),
            CONSTRAINT fk_verdicts_result_snapshot_id FOREIGN KEY (result_snapshot_id)
                REFERENCES test_result_snapshots (id),
            CONSTRAINT fk_verdicts_decision_rule_set_id FOREIGN KEY (decision_rule_set_id)
                REFERENCES decision_rule_sets (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_verdicts_test_id
        ON verdicts (test_id)
        """
    )

    op.execute(
        """
        CREATE TABLE investment_profiles (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            test_id uuid NOT NULL,
            version integer NOT NULL,
            unit_cost_minor bigint NOT NULL,
            selling_price_minor bigint NOT NULL,
            fulfillment_cost_minor bigint NOT NULL DEFAULT 0,
            payment_fee_bp integer NOT NULL DEFAULT 0,
            available_budget_minor bigint NOT NULL,
            target_margin_bp integer NOT NULL,
            supplier_moq integer NOT NULL,
            lead_time_days integer NOT NULL,
            currency char(3) NOT NULL,
            is_current boolean NOT NULL DEFAULT false,
            created_by uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_investment_profiles_test_id_version UNIQUE (test_id, version),
            CONSTRAINT ck_investment_profiles_payment_fee_bp CHECK (
                payment_fee_bp BETWEEN 0 AND 10000
            ),
            CONSTRAINT ck_investment_profiles_target_margin_bp CHECK (
                target_margin_bp BETWEEN 0 AND 10000
            ),
            CONSTRAINT ck_investment_profiles_supplier_moq CHECK (supplier_moq >= 1),
            CONSTRAINT ck_investment_profiles_lead_time_days CHECK (lead_time_days >= 0),
            CONSTRAINT fk_investment_profiles_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_investment_profiles_test_id FOREIGN KEY (test_id)
                REFERENCES tests (id),
            CONSTRAINT fk_investment_profiles_currency FOREIGN KEY (currency)
                REFERENCES currencies (code),
            CONSTRAINT fk_investment_profiles_created_by FOREIGN KEY (created_by)
                REFERENCES users (id)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_investment_profiles_test_id_current
        ON investment_profiles (test_id)
        WHERE is_current
        """
    )

    op.execute(
        """
        CREATE TABLE investment_recommendations (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            test_id uuid NOT NULL,
            investment_profile_id uuid NOT NULL,
            version integer NOT NULL,
            summary text NOT NULL,
            assumptions_snapshot jsonb NOT NULL,
            is_current boolean NOT NULL DEFAULT false,
            created_by uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_investment_recommendations_test_id_version UNIQUE (
                test_id,
                version
            ),
            CONSTRAINT fk_investment_recommendations_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_investment_recommendations_test_id FOREIGN KEY (test_id)
                REFERENCES tests (id),
            CONSTRAINT fk_investment_recommendations_investment_profile_id FOREIGN KEY (investment_profile_id)
                REFERENCES investment_profiles (id),
            CONSTRAINT fk_investment_recommendations_created_by FOREIGN KEY (created_by)
                REFERENCES users (id)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_investment_recommendations_test_id_current
        ON investment_recommendations (test_id)
        WHERE is_current
        """
    )

    op.execute(
        """
        CREATE TABLE demand_estimates (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            investment_recommendation_id uuid NOT NULL,
            low_units integer NOT NULL,
            base_units integer NOT NULL,
            high_units integer NOT NULL,
            assumptions jsonb NOT NULL,
            confidence text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_demand_estimates_low_units CHECK (low_units >= 0),
            CONSTRAINT ck_demand_estimates_base_units CHECK (base_units >= 0),
            CONSTRAINT ck_demand_estimates_high_units CHECK (high_units >= 0),
            CONSTRAINT ck_demand_estimates_range CHECK (
                low_units <= base_units AND base_units <= high_units
            ),
            CONSTRAINT ck_demand_estimates_confidence CHECK (
                confidence IN ('high', 'medium', 'low')
            ),
            CONSTRAINT fk_demand_estimates_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_demand_estimates_investment_recommendation_id FOREIGN KEY (investment_recommendation_id)
                REFERENCES investment_recommendations (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_demand_estimates_investment_recommendation_id
        ON demand_estimates (investment_recommendation_id)
        """
    )

    op.execute(
        """
        CREATE TABLE unit_economics (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            investment_recommendation_id uuid NOT NULL,
            contribution_margin_minor bigint NOT NULL,
            break_even_units numeric(12,2),
            cac_minor bigint,
            formulas jsonb NOT NULL DEFAULT '{}'::jsonb,
            is_negative_margin boolean NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_unit_economics_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_unit_economics_investment_recommendation_id FOREIGN KEY (investment_recommendation_id)
                REFERENCES investment_recommendations (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_unit_economics_investment_recommendation_id
        ON unit_economics (investment_recommendation_id)
        """
    )

    op.execute(
        """
        CREATE TABLE quantity_scenarios (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            investment_recommendation_id uuid NOT NULL,
            label text NOT NULL,
            quantity integer NOT NULL,
            inventory_cost_minor bigint NOT NULL,
            expected_units_sold_low integer NOT NULL,
            expected_units_sold_high integer NOT NULL,
            revenue_low_minor bigint NOT NULL,
            revenue_high_minor bigint NOT NULL,
            profit_low_minor bigint NOT NULL,
            profit_high_minor bigint NOT NULL,
            sell_through_low numeric(5,4) NOT NULL,
            sell_through_high numeric(5,4) NOT NULL,
            overstock_risk text NOT NULL,
            stockout_risk text NOT NULL,
            is_feasible boolean NOT NULL,
            infeasibility_reason text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_quantity_scenarios_label CHECK (
                label IN ('conservative', 'base', 'aggressive')
            ),
            CONSTRAINT ck_quantity_scenarios_quantity CHECK (quantity >= 0),
            CONSTRAINT ck_quantity_scenarios_units_range CHECK (
                expected_units_sold_low <= expected_units_sold_high
            ),
            CONSTRAINT ck_quantity_scenarios_overstock_risk CHECK (
                overstock_risk IN ('low', 'medium', 'high')
            ),
            CONSTRAINT ck_quantity_scenarios_stockout_risk CHECK (
                stockout_risk IN ('low', 'medium', 'high')
            ),
            CONSTRAINT fk_quantity_scenarios_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_quantity_scenarios_investment_recommendation_id FOREIGN KEY (investment_recommendation_id)
                REFERENCES investment_recommendations (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_quantity_scenarios_investment_recommendation_id
        ON quantity_scenarios (investment_recommendation_id)
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_decision_rule_sets_touch_updated_at
        BEFORE UPDATE ON decision_rule_sets
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_investment_profiles_touch_updated_at
        BEFORE UPDATE ON investment_profiles
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_investment_recommendations_touch_updated_at
        BEFORE UPDATE ON investment_recommendations
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_test_result_snapshots_block_mutation
        BEFORE UPDATE OR DELETE ON test_result_snapshots
        FOR EACH ROW EXECUTE FUNCTION fn_block_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_verdicts_block_mutation
        BEFORE UPDATE OR DELETE ON verdicts
        FOR EACH ROW EXECUTE FUNCTION fn_block_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS quantity_scenarios")
    op.execute("DROP TABLE IF EXISTS unit_economics")
    op.execute("DROP TABLE IF EXISTS demand_estimates")
    op.execute("DROP TABLE IF EXISTS investment_recommendations")
    op.execute("DROP TABLE IF EXISTS investment_profiles")
    op.execute("DROP TABLE IF EXISTS verdicts")
    op.execute("DROP TABLE IF EXISTS test_result_snapshots")
    op.execute("DROP TABLE IF EXISTS decision_rule_sets")
