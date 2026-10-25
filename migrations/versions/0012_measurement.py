"""DB-0.10 - measurement tables.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-25

Creates tracking sessions, append-only events, deposits, append-only
attributions, and metric snapshots, then closes the deferred
orders.tracking_session_id FK. Downgrade removes that FK first, then drops the
tables in reverse order.
"""

from __future__ import annotations

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE tracking_sessions (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            landing_page_id uuid NOT NULL,
            test_id uuid,
            campaign_id uuid,
            first_utm_source text,
            first_utm_medium text,
            first_utm_campaign text,
            first_utm_content text,
            first_utm_term text,
            referrer text,
            user_agent text NOT NULL,
            ip_hash char(64) NOT NULL,
            consent_state text NOT NULL DEFAULT 'unknown',
            started_at timestamptz NOT NULL,
            last_seen_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_tracking_sessions_consent_state CHECK (
                consent_state IN ('unknown', 'granted', 'denied')
            ),
            CONSTRAINT fk_tracking_sessions_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_tracking_sessions_landing_page_id FOREIGN KEY (landing_page_id)
                REFERENCES landing_pages (id),
            CONSTRAINT fk_tracking_sessions_test_id FOREIGN KEY (test_id)
                REFERENCES tests (id),
            CONSTRAINT fk_tracking_sessions_campaign_id FOREIGN KEY (campaign_id)
                REFERENCES campaigns (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_tracking_sessions_landing_page_id
        ON tracking_sessions (landing_page_id)
        """
    )

    op.execute(
        """
        CREATE TABLE events (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            event_id uuid NOT NULL,
            tracking_session_id uuid,
            test_id uuid,
            product_id uuid,
            campaign_id uuid,
            adset_id uuid,
            ad_variation_id uuid,
            event_type text NOT NULL,
            source text NOT NULL,
            url text,
            referrer text,
            occurred_at timestamptz NOT NULL,
            received_at timestamptz NOT NULL DEFAULT now(),
            is_bot boolean NOT NULL DEFAULT false,
            properties jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_events_event_id UNIQUE (event_id),
            CONSTRAINT ck_events_source CHECK (source IN ('web', 'server')),
            CONSTRAINT fk_events_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_events_tracking_session_id FOREIGN KEY (tracking_session_id)
                REFERENCES tracking_sessions (id),
            CONSTRAINT fk_events_test_id FOREIGN KEY (test_id)
                REFERENCES tests (id),
            CONSTRAINT fk_events_product_id FOREIGN KEY (product_id)
                REFERENCES products (id),
            CONSTRAINT fk_events_campaign_id FOREIGN KEY (campaign_id)
                REFERENCES campaigns (id),
            CONSTRAINT fk_events_adset_id FOREIGN KEY (adset_id)
                REFERENCES ad_sets (id),
            CONSTRAINT fk_events_ad_variation_id FOREIGN KEY (ad_variation_id)
                REFERENCES ad_variations (id),
            CONSTRAINT fk_events_event_type FOREIGN KEY (event_type)
                REFERENCES event_types (code)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_events_store_id_event_type_occurred_at
        ON events (store_id, event_type, occurred_at)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_events_tracking_session_id
        ON events (tracking_session_id)
        """
    )

    op.execute(
        """
        CREATE TABLE deposits (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            order_id uuid NOT NULL,
            test_id uuid,
            status text NOT NULL DEFAULT 'pending',
            amount_minor bigint NOT NULL,
            currency char(3) NOT NULL,
            method text NOT NULL,
            evidence_file_id uuid,
            external_payment_id text,
            verified_by uuid,
            verified_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_deposits_status CHECK (
                status IN ('pending', 'confirmed', 'rejected')
            ),
            CONSTRAINT ck_deposits_amount_minor CHECK (amount_minor >= 0),
            CONSTRAINT ck_deposits_method CHECK (
                method IN ('manual', 'payment_gateway')
            ),
            CONSTRAINT fk_deposits_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_deposits_order_id FOREIGN KEY (order_id)
                REFERENCES orders (id),
            CONSTRAINT fk_deposits_test_id FOREIGN KEY (test_id)
                REFERENCES tests (id),
            CONSTRAINT fk_deposits_currency FOREIGN KEY (currency)
                REFERENCES currencies (code),
            CONSTRAINT fk_deposits_evidence_file_id FOREIGN KEY (evidence_file_id)
                REFERENCES stored_files (id),
            CONSTRAINT fk_deposits_verified_by FOREIGN KEY (verified_by)
                REFERENCES users (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_deposits_order_id
        ON deposits (order_id)
        """
    )

    op.execute(
        """
        CREATE TABLE attributions (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            subject_type text NOT NULL,
            subject_id uuid NOT NULL,
            test_id uuid,
            campaign_id uuid,
            adset_id uuid,
            ad_variation_id uuid,
            model text NOT NULL,
            window_seconds integer NOT NULL,
            is_attributed boolean NOT NULL,
            confidence numeric(5,4) NOT NULL,
            resolved_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_attributions_subject_type_subject_id UNIQUE (
                subject_type,
                subject_id
            ),
            CONSTRAINT ck_attributions_subject_type CHECK (
                subject_type IN ('event', 'order')
            ),
            CONSTRAINT ck_attributions_model CHECK (
                model IN ('last_touch', 'first_touch', 'direct')
            ),
            CONSTRAINT ck_attributions_window_seconds CHECK (window_seconds > 0),
            CONSTRAINT fk_attributions_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_attributions_test_id FOREIGN KEY (test_id)
                REFERENCES tests (id),
            CONSTRAINT fk_attributions_campaign_id FOREIGN KEY (campaign_id)
                REFERENCES campaigns (id),
            CONSTRAINT fk_attributions_adset_id FOREIGN KEY (adset_id)
                REFERENCES ad_sets (id),
            CONSTRAINT fk_attributions_ad_variation_id FOREIGN KEY (ad_variation_id)
                REFERENCES ad_variations (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE metric_snapshots (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            test_id uuid NOT NULL,
            provider text NOT NULL,
            campaign_id uuid NOT NULL,
            adset_id uuid,
            ad_variation_id uuid,
            period_start timestamptz NOT NULL,
            period_end timestamptz NOT NULL,
            snapshot_at timestamptz NOT NULL,
            currency char(3) NOT NULL,
            spend_minor bigint NOT NULL,
            impressions bigint NOT NULL,
            reach bigint NOT NULL,
            frequency numeric(9,4),
            clicks bigint NOT NULL,
            ctr numeric(9,6),
            cpc_minor bigint,
            cpm_minor bigint,
            engagement bigint,
            platform_conversions bigint,
            cost_per_conversion_minor bigint,
            raw jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_metric_snapshots_campaign_window UNIQUE NULLS NOT DISTINCT (
                campaign_id,
                adset_id,
                ad_variation_id,
                period_start,
                period_end
            ),
            CONSTRAINT fk_metric_snapshots_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_metric_snapshots_test_id FOREIGN KEY (test_id)
                REFERENCES tests (id),
            CONSTRAINT fk_metric_snapshots_campaign_id FOREIGN KEY (campaign_id)
                REFERENCES campaigns (id),
            CONSTRAINT fk_metric_snapshots_adset_id FOREIGN KEY (adset_id)
                REFERENCES ad_sets (id),
            CONSTRAINT fk_metric_snapshots_ad_variation_id FOREIGN KEY (ad_variation_id)
                REFERENCES ad_variations (id),
            CONSTRAINT fk_metric_snapshots_currency FOREIGN KEY (currency)
                REFERENCES currencies (code)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_metric_snapshots_campaign_id_period_start
        ON metric_snapshots (campaign_id, period_start)
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_deposits_touch_updated_at
        BEFORE UPDATE ON deposits
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_events_block_mutation
        BEFORE UPDATE OR DELETE ON events
        FOR EACH ROW EXECUTE FUNCTION fn_block_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_attributions_block_mutation
        BEFORE UPDATE OR DELETE ON attributions
        FOR EACH ROW EXECUTE FUNCTION fn_block_mutation()
        """
    )

    op.execute(
        """
        ALTER TABLE orders
        ADD CONSTRAINT fk_orders_tracking_session_id FOREIGN KEY (tracking_session_id)
        REFERENCES tracking_sessions (id)
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE orders DROP CONSTRAINT IF EXISTS fk_orders_tracking_session_id"
    )
    op.execute("DROP TABLE IF EXISTS metric_snapshots")
    op.execute("DROP TABLE IF EXISTS attributions")
    op.execute("DROP TABLE IF EXISTS deposits")
    op.execute("DROP TABLE IF EXISTS events")
    op.execute("DROP TABLE IF EXISTS tracking_sessions")
