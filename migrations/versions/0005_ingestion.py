"""DB-0.5 - integrations and ingestion tables.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-25

Creates the integrations and data-ingestion tables in dependency order.
Cross-domain references to tables that do not exist yet (categories, tests,
landing pages, posts, campaigns, tracking sessions) remain plain columns and
get their FKs in DB-0.13. Downgrade drops the tables in reverse order.
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE store_connections (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            provider text NOT NULL,
            external_store_id text NOT NULL,
            status text NOT NULL,
            scopes text[] NOT NULL DEFAULT '{}',
            access_token_encrypted text,
            refresh_token_encrypted text,
            token_expires_at timestamptz,
            last_synced_at timestamptz,
            metadata jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_store_connections_store_id_provider UNIQUE (store_id, provider),
            CONSTRAINT ck_store_connections_status CHECK (
                status IN ('connected', 'expired', 'revoked', 'error')
            ),
            CONSTRAINT fk_store_connections_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE ad_account_connections (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            provider text NOT NULL,
            external_account_id text NOT NULL,
            account_name text,
            status text NOT NULL,
            scopes text[] NOT NULL DEFAULT '{}',
            access_token_encrypted text,
            refresh_token_encrypted text,
            token_expires_at timestamptz,
            last_synced_at timestamptz,
            metadata jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_ad_account_connections_store_id_provider_external_account_id
                UNIQUE (store_id, provider, external_account_id),
            CONSTRAINT ck_ad_account_connections_provider CHECK (
                provider IN ('meta', 'tiktok', 'google', 'snapchat')
            ),
            CONSTRAINT ck_ad_account_connections_status CHECK (
                status IN ('connected', 'expired', 'revoked', 'error')
            ),
            CONSTRAINT fk_ad_account_connections_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE content_providers (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid,
            code text NOT NULL,
            name text NOT NULL,
            media_types text[] NOT NULL DEFAULT '{}',
            auth_config_encrypted text,
            rate_limits jsonb,
            pricing jsonb,
            capabilities jsonb,
            enabled boolean NOT NULL DEFAULT true,
            is_default boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_content_providers_store_id_code UNIQUE (store_id, code),
            CONSTRAINT fk_content_providers_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_content_providers_code_platform
        ON content_providers (code)
        WHERE store_id IS NULL
        """
    )

    op.execute(
        """
        CREATE TABLE content_generation_jobs (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            content_provider_id uuid NOT NULL,
            type text NOT NULL,
            prompt text NOT NULL,
            negative_prompt text,
            params jsonb,
            status text NOT NULL,
            requested_by uuid NOT NULL,
            result_creative_ids uuid[] NOT NULL DEFAULT '{}',
            cost_minor bigint,
            currency char(3),
            error_code text,
            error_message text,
            async_job_id uuid,
            started_at timestamptz,
            finished_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_content_generation_jobs_type CHECK (
                type IN ('image', 'video')
            ),
            CONSTRAINT ck_content_generation_jobs_status CHECK (
                status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')
            ),
            CONSTRAINT fk_content_generation_jobs_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_content_generation_jobs_content_provider_id FOREIGN KEY (content_provider_id)
                REFERENCES content_providers (id),
            CONSTRAINT fk_content_generation_jobs_requested_by FOREIGN KEY (requested_by)
                REFERENCES users (id),
            CONSTRAINT fk_content_generation_jobs_async_job_id FOREIGN KEY (async_job_id)
                REFERENCES async_jobs (id),
            CONSTRAINT fk_content_generation_jobs_currency FOREIGN KEY (currency)
                REFERENCES currencies (code)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE stored_files (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            purpose text NOT NULL,
            original_filename text NOT NULL,
            mime_type text NOT NULL,
            size_bytes bigint NOT NULL,
            checksum_sha256 char(64) NOT NULL,
            storage_provider text NOT NULL,
            storage_key text NOT NULL,
            status text NOT NULL,
            uploaded_by_user_id uuid,
            metadata jsonb,
            deleted_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_stored_files_purpose CHECK (
                purpose IN (
                    'sales_csv',
                    'feedback_file',
                    'product_image',
                    'ad_creative',
                    'deposit_evidence',
                    'ai_image',
                    'ai_video',
                    'creative'
                )
            ),
            CONSTRAINT ck_stored_files_size_bytes CHECK (size_bytes >= 0),
            CONSTRAINT ck_stored_files_status CHECK (
                status IN ('staged', 'committed', 'deleted')
            ),
            CONSTRAINT fk_stored_files_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_stored_files_uploaded_by_user_id FOREIGN KEY (uploaded_by_user_id)
                REFERENCES users (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE column_mappings (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            name text NOT NULL,
            source_type text NOT NULL,
            mapping jsonb NOT NULL,
            is_default boolean NOT NULL DEFAULT false,
            created_by uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_column_mappings_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_column_mappings_created_by FOREIGN KEY (created_by)
                REFERENCES users (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE import_batches (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            source_type text NOT NULL,
            stored_file_id uuid,
            store_connection_id uuid,
            column_mapping_id uuid,
            status text NOT NULL,
            strict_mode boolean NOT NULL DEFAULT true,
            date_range_start date,
            date_range_end date,
            total_rows integer NOT NULL DEFAULT 0,
            valid_rows integer NOT NULL DEFAULT 0,
            invalid_rows integer NOT NULL DEFAULT 0,
            duplicate_rows integer NOT NULL DEFAULT 0,
            imported_rows integer NOT NULL DEFAULT 0,
            skipped_rows integer NOT NULL DEFAULT 0,
            error_report_file_id uuid,
            started_at timestamptz,
            completed_at timestamptz,
            created_by uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_import_batches_source_type CHECK (
                source_type IN ('csv', 'store_connection')
            ),
            CONSTRAINT ck_import_batches_status CHECK (
                status IN (
                    'uploaded',
                    'mapping',
                    'validating',
                    'preview',
                    'committing',
                    'completed',
                    'failed',
                    'cancelled'
                )
            ),
            CONSTRAINT ck_import_batches_source CHECK (
                (source_type = 'csv' AND stored_file_id IS NOT NULL)
                OR (source_type = 'store_connection' AND store_connection_id IS NOT NULL)
            ),
            CONSTRAINT fk_import_batches_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_import_batches_stored_file_id FOREIGN KEY (stored_file_id)
                REFERENCES stored_files (id),
            CONSTRAINT fk_import_batches_store_connection_id FOREIGN KEY (store_connection_id)
                REFERENCES store_connections (id),
            CONSTRAINT fk_import_batches_column_mapping_id FOREIGN KEY (column_mapping_id)
                REFERENCES column_mappings (id),
            CONSTRAINT fk_import_batches_error_report_file_id FOREIGN KEY (error_report_file_id)
                REFERENCES stored_files (id),
            CONSTRAINT fk_import_batches_created_by FOREIGN KEY (created_by)
                REFERENCES users (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE products (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            external_product_id text,
            sku text,
            name text NOT NULL,
            description text,
            category_id uuid,
            currency char(3) NOT NULL,
            cost_minor bigint,
            price_minor bigint,
            image_file_id uuid,
            status text NOT NULL DEFAULT 'active',
            source text NOT NULL,
            metadata jsonb,
            deleted_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_products_status CHECK (status IN ('active', 'archived')),
            CONSTRAINT ck_products_source CHECK (source IN ('imported', 'manual', 'concept')),
            CONSTRAINT fk_products_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_products_currency FOREIGN KEY (currency)
                REFERENCES currencies (code),
            CONSTRAINT fk_products_image_file_id FOREIGN KEY (image_file_id)
                REFERENCES stored_files (id)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_products_store_id_external_product_id
        ON products (store_id, external_product_id)
        WHERE external_product_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_products_store_id_sku
        ON products (store_id, sku)
        WHERE sku IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_products_store_id_status
        ON products (store_id, status)
        """
    )

    op.execute(
        """
        CREATE TABLE orders (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            origin text NOT NULL,
            external_order_id text,
            order_number text,
            test_id uuid,
            test_phase text,
            status text NOT NULL,
            currency char(3) NOT NULL,
            subtotal_minor bigint NOT NULL DEFAULT 0,
            shipping_minor bigint NOT NULL DEFAULT 0,
            discount_minor bigint NOT NULL DEFAULT 0,
            total_minor bigint NOT NULL DEFAULT 0,
            customer_name text,
            customer_phone text,
            customer_address_enc bytea,
            landing_page_id uuid,
            post_id uuid,
            campaign_id uuid,
            tracking_session_id uuid,
            import_batch_id uuid,
            dedupe_hash char(64),
            placed_at timestamptz NOT NULL,
            imported_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_orders_origin CHECK (origin IN ('imported', 'cod')),
            CONSTRAINT ck_orders_test_phase CHECK (
                test_phase IN ('before_test', 'during_test', 'after_test')
            ),
            CONSTRAINT ck_orders_status CHECK (
                status IN ('pending', 'confirmed', 'fulfilled', 'cancelled', 'returned')
            ),
            CONSTRAINT fk_orders_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_orders_currency FOREIGN KEY (currency)
                REFERENCES currencies (code),
            CONSTRAINT fk_orders_import_batch_id FOREIGN KEY (import_batch_id)
                REFERENCES import_batches (id)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_orders_store_id_external_order_id
        ON orders (store_id, external_order_id)
        WHERE external_order_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_orders_store_id_dedupe_hash
        ON orders (store_id, dedupe_hash)
        WHERE dedupe_hash IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_orders_store_id_test_id_test_phase
        ON orders (store_id, test_id, test_phase)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_orders_store_id_placed_at
        ON orders (store_id, placed_at)
        """
    )

    op.execute(
        """
        CREATE TABLE order_items (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            order_id uuid NOT NULL,
            product_id uuid,
            product_external_id text,
            product_name_snapshot text NOT NULL,
            sku_snapshot text,
            quantity integer NOT NULL,
            unit_price_minor bigint NOT NULL,
            line_total_minor bigint NOT NULL,
            currency char(3) NOT NULL,
            metadata jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_order_items_quantity CHECK (quantity > 0),
            CONSTRAINT fk_order_items_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_order_items_order_id FOREIGN KEY (order_id)
                REFERENCES orders (id),
            CONSTRAINT fk_order_items_product_id FOREIGN KEY (product_id)
                REFERENCES products (id),
            CONSTRAINT fk_order_items_currency FOREIGN KEY (currency)
                REFERENCES currencies (code)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE import_rows (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            import_batch_id uuid NOT NULL,
            row_number integer NOT NULL,
            raw_data jsonb NOT NULL,
            normalized_data jsonb,
            status text NOT NULL,
            issue_count integer NOT NULL DEFAULT 0,
            created_order_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_import_rows_import_batch_id_row_number UNIQUE (
                import_batch_id,
                row_number
            ),
            CONSTRAINT ck_import_rows_status CHECK (
                status IN ('valid', 'invalid', 'duplicate', 'imported', 'skipped')
            ),
            CONSTRAINT fk_import_rows_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_import_rows_import_batch_id FOREIGN KEY (import_batch_id)
                REFERENCES import_batches (id),
            CONSTRAINT fk_import_rows_created_order_id FOREIGN KEY (created_order_id)
                REFERENCES orders (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE import_issues (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            import_batch_id uuid NOT NULL,
            import_row_id uuid,
            row_number integer NOT NULL,
            field_name text,
            issue_code text NOT NULL,
            severity text NOT NULL,
            message text NOT NULL,
            raw_value text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_import_issues_severity CHECK (
                severity IN ('error', 'warning')
            ),
            CONSTRAINT fk_import_issues_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_import_issues_import_batch_id FOREIGN KEY (import_batch_id)
                REFERENCES import_batches (id),
            CONSTRAINT fk_import_issues_import_row_id FOREIGN KEY (import_row_id)
                REFERENCES import_rows (id)
        )
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_store_connections_touch_updated_at
        BEFORE UPDATE ON store_connections
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ad_account_connections_touch_updated_at
        BEFORE UPDATE ON ad_account_connections
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_content_providers_touch_updated_at
        BEFORE UPDATE ON content_providers
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_column_mappings_touch_updated_at
        BEFORE UPDATE ON column_mappings
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_import_batches_touch_updated_at
        BEFORE UPDATE ON import_batches
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_products_touch_updated_at
        BEFORE UPDATE ON products
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_orders_touch_updated_at
        BEFORE UPDATE ON orders
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS import_issues")
    op.execute("DROP TABLE IF EXISTS import_rows")
    op.execute("DROP TABLE IF EXISTS order_items")
    op.execute("DROP TABLE IF EXISTS orders")
    op.execute("DROP TABLE IF EXISTS products")
    op.execute("DROP TABLE IF EXISTS import_batches")
    op.execute("DROP TABLE IF EXISTS column_mappings")
    op.execute("DROP TABLE IF EXISTS stored_files")
    op.execute("DROP TABLE IF EXISTS content_generation_jobs")
    op.execute("DROP TABLE IF EXISTS content_providers")
    op.execute("DROP TABLE IF EXISTS ad_account_connections")
    op.execute("DROP TABLE IF EXISTS store_connections")
