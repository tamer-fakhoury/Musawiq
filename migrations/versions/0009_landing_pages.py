"""DB-0.9a - landing pages and order channels.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-25

Creates page templates, landing pages, page versions, and order channels.
The landing_pages <-> page_versions and landing_pages <-> order_channels
circular FKs are added via ALTER after all four tables exist. test_id and
post_id stay deferred until their tables land. Downgrade removes the four
ALTER-added FKs first, then drops the tables in reverse order.
"""

from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE page_templates (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            key text NOT NULL,
            version integer NOT NULL,
            name text NOT NULL,
            is_active boolean NOT NULL DEFAULT true,
            schema jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_page_templates_key_version UNIQUE (key, version)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE landing_pages (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            product_concept_id uuid NOT NULL,
            test_id uuid,
            slug text NOT NULL,
            status text NOT NULL DEFAULT 'draft',
            template_id uuid NOT NULL,
            current_version_id uuid,
            published_version_id uuid,
            order_channel_id uuid,
            language text NOT NULL,
            currency char(3) NOT NULL,
            published_url text,
            published_at timestamptz,
            deleted_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_landing_pages_slug UNIQUE (slug),
            CONSTRAINT ck_landing_pages_status CHECK (
                status IN ('draft', 'published', 'unpublished')
            ),
            CONSTRAINT fk_landing_pages_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_landing_pages_product_concept_id FOREIGN KEY (product_concept_id)
                REFERENCES product_concepts (id),
            CONSTRAINT fk_landing_pages_template_id FOREIGN KEY (template_id)
                REFERENCES page_templates (id),
            CONSTRAINT fk_landing_pages_language FOREIGN KEY (language)
                REFERENCES languages (code),
            CONSTRAINT fk_landing_pages_currency FOREIGN KEY (currency)
                REFERENCES currencies (code)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE page_versions (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            landing_page_id uuid NOT NULL,
            version integer NOT NULL,
            content jsonb NOT NULL,
            price_minor bigint NOT NULL,
            currency char(3) NOT NULL,
            image_file_ids uuid[] NOT NULL DEFAULT '{}',
            order_channel_id uuid,
            generated_by text NOT NULL,
            model_version text,
            created_by uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_page_versions_landing_page_id_version UNIQUE (
                landing_page_id,
                version
            ),
            CONSTRAINT ck_page_versions_generated_by CHECK (
                generated_by IN ('ai', 'manual')
            ),
            CONSTRAINT fk_page_versions_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_page_versions_landing_page_id FOREIGN KEY (landing_page_id)
                REFERENCES landing_pages (id),
            CONSTRAINT fk_page_versions_currency FOREIGN KEY (currency)
                REFERENCES currencies (code),
            CONSTRAINT fk_page_versions_created_by FOREIGN KEY (created_by)
                REFERENCES users (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE order_channels (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            landing_page_id uuid,
            post_id uuid,
            type text NOT NULL,
            whatsapp_number text,
            whatsapp_message_template text,
            cod_form_schema jsonb,
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_order_channels_type CHECK (type IN ('whatsapp', 'cod')),
            CONSTRAINT ck_order_channels_target CHECK (
                (landing_page_id IS NOT NULL) <> (post_id IS NOT NULL)
            ),
            CONSTRAINT ck_order_channels_payload CHECK (
                (type = 'whatsapp' AND whatsapp_number IS NOT NULL)
                OR (type = 'cod' AND cod_form_schema IS NOT NULL)
            ),
            CONSTRAINT fk_order_channels_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_order_channels_landing_page_id FOREIGN KEY (landing_page_id)
                REFERENCES landing_pages (id)
        )
        """
    )

    op.execute(
        """
        CREATE INDEX ix_landing_pages_store_id_status
        ON landing_pages (store_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_order_channels_landing_page_id
        ON order_channels (landing_page_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_order_channels_post_id
        ON order_channels (post_id)
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_page_templates_touch_updated_at
        BEFORE UPDATE ON page_templates
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_landing_pages_touch_updated_at
        BEFORE UPDATE ON landing_pages
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_order_channels_touch_updated_at
        BEFORE UPDATE ON order_channels
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )

    op.execute(
        """
        ALTER TABLE landing_pages
        ADD CONSTRAINT fk_landing_pages_current_version_id FOREIGN KEY (current_version_id)
        REFERENCES page_versions (id)
        """
    )
    op.execute(
        """
        ALTER TABLE landing_pages
        ADD CONSTRAINT fk_landing_pages_published_version_id FOREIGN KEY (published_version_id)
        REFERENCES page_versions (id)
        """
    )
    op.execute(
        """
        ALTER TABLE landing_pages
        ADD CONSTRAINT fk_landing_pages_order_channel_id FOREIGN KEY (order_channel_id)
        REFERENCES order_channels (id)
        """
    )
    op.execute(
        """
        ALTER TABLE page_versions
        ADD CONSTRAINT fk_page_versions_order_channel_id FOREIGN KEY (order_channel_id)
        REFERENCES order_channels (id)
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE page_versions DROP CONSTRAINT IF EXISTS fk_page_versions_order_channel_id"
    )
    op.execute(
        "ALTER TABLE landing_pages DROP CONSTRAINT IF EXISTS fk_landing_pages_order_channel_id"
    )
    op.execute(
        "ALTER TABLE landing_pages DROP CONSTRAINT IF EXISTS fk_landing_pages_published_version_id"
    )
    op.execute(
        "ALTER TABLE landing_pages DROP CONSTRAINT IF EXISTS fk_landing_pages_current_version_id"
    )
    op.execute("DROP TABLE IF EXISTS order_channels")
    op.execute("DROP TABLE IF EXISTS page_versions")
    op.execute("DROP TABLE IF EXISTS landing_pages")
    op.execute("DROP TABLE IF EXISTS page_templates")
