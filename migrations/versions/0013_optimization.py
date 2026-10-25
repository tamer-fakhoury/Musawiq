"""DB-0.11 - optimization tables.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-25

Creates optimization rule sets, performance findings, recommendations,
executed actions, budget policies, and alerts. Downgrade drops the tables in
reverse order.
"""

from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE optimization_rule_sets (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid,
            scope text NOT NULL,
            campaign_id uuid,
            version integer NOT NULL,
            is_active boolean NOT NULL DEFAULT true,
            min_impressions integer NOT NULL DEFAULT 0,
            min_clicks integer NOT NULL DEFAULT 0,
            min_conversions integer NOT NULL DEFAULT 0,
            ctr_floor numeric(9,6),
            cpc_ceiling_minor bigint,
            cost_per_conversion_ceiling_minor bigint,
            rules jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_by uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_optimization_rule_sets_scope CHECK (
                scope IN ('global', 'store', 'campaign')
            ),
            CONSTRAINT ck_optimization_rule_sets_campaign_scope CHECK (
                scope <> 'campaign' OR campaign_id IS NOT NULL
            ),
            CONSTRAINT uq_optimization_rule_sets_natural_key UNIQUE NULLS NOT DISTINCT (
                store_id,
                scope,
                campaign_id,
                version
            ),
            CONSTRAINT fk_optimization_rule_sets_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_optimization_rule_sets_campaign_id FOREIGN KEY (campaign_id)
                REFERENCES campaigns (id),
            CONSTRAINT fk_optimization_rule_sets_created_by FOREIGN KEY (created_by)
                REFERENCES users (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_optimization_rule_sets_store_id_scope
        ON optimization_rule_sets (store_id, scope)
        """
    )

    op.execute(
        """
        CREATE TABLE performance_findings (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            campaign_id uuid NOT NULL,
            adset_id uuid,
            ad_variation_id uuid,
            rule_set_id uuid NOT NULL,
            status text NOT NULL,
            metric_key text NOT NULL,
            observed_value numeric NOT NULL,
            threshold_value numeric NOT NULL,
            reason_code text NOT NULL,
            data_window_start timestamptz NOT NULL,
            data_window_end timestamptz NOT NULL,
            evaluated_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_performance_findings_status CHECK (
                status IN ('underperforming', 'promising', 'insufficient_data')
            ),
            CONSTRAINT fk_performance_findings_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_performance_findings_campaign_id FOREIGN KEY (campaign_id)
                REFERENCES campaigns (id),
            CONSTRAINT fk_performance_findings_adset_id FOREIGN KEY (adset_id)
                REFERENCES ad_sets (id),
            CONSTRAINT fk_performance_findings_ad_variation_id FOREIGN KEY (ad_variation_id)
                REFERENCES ad_variations (id),
            CONSTRAINT fk_performance_findings_rule_set_id FOREIGN KEY (rule_set_id)
                REFERENCES optimization_rule_sets (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_performance_findings_campaign_id_evaluated_at
        ON performance_findings (campaign_id, evaluated_at DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE optimization_recommendations (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            finding_id uuid,
            campaign_id uuid NOT NULL,
            adset_id uuid,
            ad_variation_id uuid,
            action text NOT NULL,
            rationale text NOT NULL,
            proposed_changes jsonb NOT NULL DEFAULT '{}'::jsonb,
            expected_impact jsonb NOT NULL DEFAULT '{}'::jsonb,
            budget_impact_minor bigint NOT NULL DEFAULT 0,
            currency char(3) NOT NULL,
            status text NOT NULL DEFAULT 'pending',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_optimization_recommendations_action CHECK (
                action IN (
                    'pause',
                    'keep',
                    'reallocate',
                    'increase_budget',
                    'decrease_budget'
                )
            ),
            CONSTRAINT ck_optimization_recommendations_status CHECK (
                status IN ('pending', 'accepted', 'dismissed', 'executed', 'expired')
            ),
            CONSTRAINT fk_optimization_recommendations_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_optimization_recommendations_finding_id FOREIGN KEY (finding_id)
                REFERENCES performance_findings (id),
            CONSTRAINT fk_optimization_recommendations_campaign_id FOREIGN KEY (campaign_id)
                REFERENCES campaigns (id),
            CONSTRAINT fk_optimization_recommendations_adset_id FOREIGN KEY (adset_id)
                REFERENCES ad_sets (id),
            CONSTRAINT fk_optimization_recommendations_ad_variation_id FOREIGN KEY (ad_variation_id)
                REFERENCES ad_variations (id),
            CONSTRAINT fk_optimization_recommendations_currency FOREIGN KEY (currency)
                REFERENCES currencies (code)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_optimization_recommendations_campaign_id_status
        ON optimization_recommendations (campaign_id, status)
        """
    )

    op.execute(
        """
        CREATE TABLE optimization_actions (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            recommendation_id uuid,
            campaign_id uuid NOT NULL,
            adset_id uuid,
            ad_variation_id uuid,
            action_type text NOT NULL,
            actor_type text NOT NULL,
            actor_user_id uuid,
            before_state jsonb,
            after_state jsonb,
            reason text,
            external_reference text,
            status text NOT NULL,
            executed_at timestamptz NOT NULL,
            reverted_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_optimization_actions_actor_type CHECK (
                actor_type IN ('user', 'system')
            ),
            CONSTRAINT ck_optimization_actions_status CHECK (
                status IN ('succeeded', 'failed', 'reverted')
            ),
            CONSTRAINT fk_optimization_actions_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_optimization_actions_recommendation_id FOREIGN KEY (recommendation_id)
                REFERENCES optimization_recommendations (id),
            CONSTRAINT fk_optimization_actions_campaign_id FOREIGN KEY (campaign_id)
                REFERENCES campaigns (id),
            CONSTRAINT fk_optimization_actions_adset_id FOREIGN KEY (adset_id)
                REFERENCES ad_sets (id),
            CONSTRAINT fk_optimization_actions_ad_variation_id FOREIGN KEY (ad_variation_id)
                REFERENCES ad_variations (id),
            CONSTRAINT fk_optimization_actions_actor_user_id FOREIGN KEY (actor_user_id)
                REFERENCES users (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_optimization_actions_campaign_id
        ON optimization_actions (campaign_id)
        """
    )

    op.execute(
        """
        CREATE TABLE budget_policies (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            test_id uuid,
            campaign_id uuid,
            total_cap_minor bigint NOT NULL,
            daily_cap_minor bigint NOT NULL,
            currency char(3) NOT NULL,
            enforcement text NOT NULL DEFAULT 'hard',
            is_active boolean NOT NULL DEFAULT true,
            created_by uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_budget_policies_target CHECK (
                test_id IS NOT NULL OR campaign_id IS NOT NULL
            ),
            CONSTRAINT ck_budget_policies_enforcement CHECK (
                enforcement IN ('hard', 'soft')
            ),
            CONSTRAINT fk_budget_policies_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_budget_policies_test_id FOREIGN KEY (test_id)
                REFERENCES tests (id),
            CONSTRAINT fk_budget_policies_campaign_id FOREIGN KEY (campaign_id)
                REFERENCES campaigns (id),
            CONSTRAINT fk_budget_policies_currency FOREIGN KEY (currency)
                REFERENCES currencies (code),
            CONSTRAINT fk_budget_policies_created_by FOREIGN KEY (created_by)
                REFERENCES users (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE alerts (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            type text NOT NULL,
            severity text NOT NULL,
            title text NOT NULL,
            message text NOT NULL,
            related_type text,
            related_id uuid,
            status text NOT NULL DEFAULT 'open',
            acknowledged_by uuid,
            resolved_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_alerts_type CHECK (
                type IN ('overspend', 'sync_failure', 'anomaly', 'publication_failure')
            ),
            CONSTRAINT ck_alerts_severity CHECK (
                severity IN ('info', 'warning', 'critical')
            ),
            CONSTRAINT ck_alerts_status CHECK (
                status IN ('open', 'acknowledged', 'resolved')
            ),
            CONSTRAINT fk_alerts_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_alerts_acknowledged_by FOREIGN KEY (acknowledged_by)
                REFERENCES users (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_alerts_store_id_status
        ON alerts (store_id, status)
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_optimization_rule_sets_touch_updated_at
        BEFORE UPDATE ON optimization_rule_sets
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_optimization_recommendations_touch_updated_at
        BEFORE UPDATE ON optimization_recommendations
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_budget_policies_touch_updated_at
        BEFORE UPDATE ON budget_policies
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_alerts_touch_updated_at
        BEFORE UPDATE ON alerts
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS alerts")
    op.execute("DROP TABLE IF EXISTS budget_policies")
    op.execute("DROP TABLE IF EXISTS optimization_actions")
    op.execute("DROP TABLE IF EXISTS optimization_recommendations")
    op.execute("DROP TABLE IF EXISTS performance_findings")
    op.execute("DROP TABLE IF EXISTS optimization_rule_sets")
