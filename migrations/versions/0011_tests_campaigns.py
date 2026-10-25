"""DB-0.9c - tests, campaigns, and ads.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-25

Creates the tests/campaign/ad hierarchy, tracking links, and publication
attempts, then closes the deferred test_id FKs on orders, landing_pages, and
posts. Downgrade drops those three FKs first, then the tables in reverse order.
"""

from __future__ import annotations

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

TEST_STATUSES = "'draft', 'running', 'paused', 'awaiting_verdict', 'completed', 'extended', 'cancelled'"
CAMPAIGN_STATUSES = "'draft', 'submitted', 'active', 'paused', 'rejected', 'failed', 'completed'"
AD_VARIATION_STATUSES = "'draft', 'approved', 'discarded', 'submitted', 'active', 'paused', 'rejected', 'failed'"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE tests (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            product_concept_id uuid NOT NULL,
            landing_page_id uuid,
            post_id uuid,
            name text NOT NULL,
            status text NOT NULL DEFAULT 'draft',
            primary_conversion text NOT NULL,
            currency char(3) NOT NULL,
            total_budget_minor bigint NOT NULL,
            daily_budget_minor bigint NOT NULL,
            spend_minor bigint NOT NULL DEFAULT 0,
            planned_start_at timestamptz NOT NULL,
            planned_end_at timestamptz NOT NULL,
            actual_start_at timestamptz,
            actual_end_at timestamptz,
            created_by uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_tests_status CHECK (status IN ({TEST_STATUSES})),
            CONSTRAINT ck_tests_primary_conversion CHECK (
                primary_conversion IN ('whatsapp_click', 'cod_order', 'deposit_confirmed')
            ),
            CONSTRAINT ck_tests_target CHECK (
                (landing_page_id IS NOT NULL AND post_id IS NULL)
                OR (landing_page_id IS NULL AND post_id IS NOT NULL)
                OR (status = 'draft')
            ),
            CONSTRAINT ck_tests_planned_window CHECK (planned_end_at > planned_start_at),
            CONSTRAINT fk_tests_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_tests_product_concept_id FOREIGN KEY (product_concept_id)
                REFERENCES product_concepts (id),
            CONSTRAINT fk_tests_landing_page_id FOREIGN KEY (landing_page_id)
                REFERENCES landing_pages (id),
            CONSTRAINT fk_tests_post_id FOREIGN KEY (post_id)
                REFERENCES posts (id),
            CONSTRAINT fk_tests_currency FOREIGN KEY (currency)
                REFERENCES currencies (code),
            CONSTRAINT fk_tests_created_by FOREIGN KEY (created_by)
                REFERENCES users (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE test_extensions (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            test_id uuid NOT NULL,
            previous_end_at timestamptz NOT NULL,
            new_end_at timestamptz NOT NULL,
            added_budget_minor bigint NOT NULL,
            currency char(3) NOT NULL,
            reason text,
            approved_by uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_test_extensions_window CHECK (new_end_at > previous_end_at),
            CONSTRAINT fk_test_extensions_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_test_extensions_test_id FOREIGN KEY (test_id)
                REFERENCES tests (id),
            CONSTRAINT fk_test_extensions_currency FOREIGN KEY (currency)
                REFERENCES currencies (code),
            CONSTRAINT fk_test_extensions_approved_by FOREIGN KEY (approved_by)
                REFERENCES users (id)
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE campaigns (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            test_id uuid NOT NULL,
            provider text NOT NULL,
            external_campaign_id text,
            name text NOT NULL,
            objective text NOT NULL,
            status text NOT NULL DEFAULT 'draft',
            budget_type text NOT NULL,
            budget_minor bigint NOT NULL,
            currency char(3) NOT NULL,
            start_at timestamptz NOT NULL,
            end_at timestamptz NOT NULL,
            created_by uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_campaigns_status CHECK (status IN ({CAMPAIGN_STATUSES})),
            CONSTRAINT ck_campaigns_budget_type CHECK (budget_type IN ('daily', 'total')),
            CONSTRAINT fk_campaigns_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_campaigns_test_id FOREIGN KEY (test_id)
                REFERENCES tests (id),
            CONSTRAINT fk_campaigns_currency FOREIGN KEY (currency)
                REFERENCES currencies (code),
            CONSTRAINT fk_campaigns_created_by FOREIGN KEY (created_by)
                REFERENCES users (id)
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE ad_sets (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            campaign_id uuid NOT NULL,
            external_adset_id text,
            name text NOT NULL,
            status text NOT NULL,
            targeting jsonb NOT NULL,
            budget_type text,
            budget_minor bigint,
            currency char(3) NOT NULL,
            start_at timestamptz NOT NULL,
            end_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_ad_sets_status CHECK (status IN ({CAMPAIGN_STATUSES})),
            CONSTRAINT ck_ad_sets_budget_type CHECK (budget_type IN ('daily', 'total')),
            CONSTRAINT fk_ad_sets_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_ad_sets_campaign_id FOREIGN KEY (campaign_id)
                REFERENCES campaigns (id),
            CONSTRAINT fk_ad_sets_currency FOREIGN KEY (currency)
                REFERENCES currencies (code)
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE ad_variations (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            adset_id uuid NOT NULL,
            external_ad_id text,
            name text,
            copy_text text NOT NULL,
            headline text,
            description text,
            creative_file_id uuid,
            primary_creative_id uuid,
            post_id uuid,
            destination_url text,
            status text NOT NULL DEFAULT 'draft',
            rejection_reason text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_ad_variations_status CHECK (status IN ({AD_VARIATION_STATUSES})),
            CONSTRAINT ck_ad_variations_target CHECK (
                post_id IS NOT NULL OR destination_url IS NOT NULL
            ),
            CONSTRAINT fk_ad_variations_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_ad_variations_adset_id FOREIGN KEY (adset_id)
                REFERENCES ad_sets (id),
            CONSTRAINT fk_ad_variations_creative_file_id FOREIGN KEY (creative_file_id)
                REFERENCES stored_files (id),
            CONSTRAINT fk_ad_variations_primary_creative_id FOREIGN KEY (primary_creative_id)
                REFERENCES creatives (id),
            CONSTRAINT fk_ad_variations_post_id FOREIGN KEY (post_id)
                REFERENCES posts (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE tracking_links (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            test_id uuid NOT NULL,
            campaign_id uuid NOT NULL,
            adset_id uuid,
            ad_variation_id uuid,
            landing_page_id uuid,
            post_id uuid,
            token text NOT NULL,
            utm_source text,
            utm_medium text,
            utm_campaign text,
            utm_content text,
            utm_term text,
            destination_url text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_tracking_links_token UNIQUE (token),
            CONSTRAINT ck_tracking_links_target CHECK (
                landing_page_id IS NOT NULL OR post_id IS NOT NULL
            ),
            CONSTRAINT fk_tracking_links_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_tracking_links_test_id FOREIGN KEY (test_id)
                REFERENCES tests (id),
            CONSTRAINT fk_tracking_links_campaign_id FOREIGN KEY (campaign_id)
                REFERENCES campaigns (id),
            CONSTRAINT fk_tracking_links_adset_id FOREIGN KEY (adset_id)
                REFERENCES ad_sets (id),
            CONSTRAINT fk_tracking_links_ad_variation_id FOREIGN KEY (ad_variation_id)
                REFERENCES ad_variations (id),
            CONSTRAINT fk_tracking_links_landing_page_id FOREIGN KEY (landing_page_id)
                REFERENCES landing_pages (id),
            CONSTRAINT fk_tracking_links_post_id FOREIGN KEY (post_id)
                REFERENCES posts (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE publication_attempts (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            campaign_id uuid,
            adset_id uuid,
            ad_variation_id uuid,
            provider text NOT NULL,
            attempt_number integer NOT NULL,
            status text NOT NULL,
            external_id text,
            request_payload jsonb,
            response_payload jsonb,
            error_code text,
            error_message text,
            submitted_by uuid NOT NULL,
            submitted_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_publication_attempts_attempt_number CHECK (attempt_number > 0),
            CONSTRAINT ck_publication_attempts_status CHECK (
                status IN ('pending', 'submitted', 'succeeded', 'failed')
            ),
            CONSTRAINT ck_publication_attempts_target CHECK (
                (campaign_id IS NOT NULL)::integer
                + (adset_id IS NOT NULL)::integer
                + (ad_variation_id IS NOT NULL)::integer = 1
            ),
            CONSTRAINT fk_publication_attempts_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_publication_attempts_campaign_id FOREIGN KEY (campaign_id)
                REFERENCES campaigns (id),
            CONSTRAINT fk_publication_attempts_adset_id FOREIGN KEY (adset_id)
                REFERENCES ad_sets (id),
            CONSTRAINT fk_publication_attempts_ad_variation_id FOREIGN KEY (ad_variation_id)
                REFERENCES ad_variations (id),
            CONSTRAINT fk_publication_attempts_submitted_by FOREIGN KEY (submitted_by)
                REFERENCES users (id)
        )
        """
    )

    op.execute(
        """
        CREATE INDEX ix_tests_store_id_status
        ON tests (store_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_test_extensions_test_id
        ON test_extensions (test_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_campaigns_test_id_status
        ON campaigns (test_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_ad_sets_campaign_id
        ON ad_sets (campaign_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_ad_variations_adset_id_status
        ON ad_variations (adset_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_tracking_links_campaign_id
        ON tracking_links (campaign_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_publication_attempts_campaign_id
        ON publication_attempts (campaign_id)
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_tests_touch_updated_at
        BEFORE UPDATE ON tests
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_campaigns_touch_updated_at
        BEFORE UPDATE ON campaigns
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ad_sets_touch_updated_at
        BEFORE UPDATE ON ad_sets
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ad_variations_touch_updated_at
        BEFORE UPDATE ON ad_variations
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )

    op.execute(
        """
        ALTER TABLE orders
        ADD CONSTRAINT fk_orders_test_id FOREIGN KEY (test_id)
        REFERENCES tests (id)
        """
    )
    op.execute(
        """
        ALTER TABLE landing_pages
        ADD CONSTRAINT fk_landing_pages_test_id FOREIGN KEY (test_id)
        REFERENCES tests (id)
        """
    )
    op.execute(
        """
        ALTER TABLE posts
        ADD CONSTRAINT fk_posts_test_id FOREIGN KEY (test_id)
        REFERENCES tests (id)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE posts DROP CONSTRAINT IF EXISTS fk_posts_test_id")
    op.execute(
        "ALTER TABLE landing_pages DROP CONSTRAINT IF EXISTS fk_landing_pages_test_id"
    )
    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS fk_orders_test_id")
    op.execute("DROP TABLE IF EXISTS publication_attempts")
    op.execute("DROP TABLE IF EXISTS tracking_links")
    op.execute("DROP TABLE IF EXISTS ad_variations")
    op.execute("DROP TABLE IF EXISTS ad_sets")
    op.execute("DROP TABLE IF EXISTS campaigns")
    op.execute("DROP TABLE IF EXISTS test_extensions")
    op.execute("DROP TABLE IF EXISTS tests")
