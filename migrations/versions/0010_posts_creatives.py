"""DB-0.9b - posts and creatives.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-25

Creates creatives, posts, post_creatives, and creative_variants, then adds the
deferred order_channels.post_id FK now that posts exists. Downgrade drops that
FK first, then the tables in reverse order.
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE creatives (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            source text NOT NULL,
            type text NOT NULL,
            stored_file_id uuid,
            external_url text,
            content_generation_job_id uuid,
            width integer,
            height integer,
            duration_ms integer,
            aspect_ratio text,
            alt_text text,
            prompt text,
            model_version text,
            status text NOT NULL DEFAULT 'draft',
            approval_state text NOT NULL DEFAULT 'pending',
            metadata jsonb,
            deleted_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_creatives_source CHECK (
                source IN ('uploaded', 'ai_generated')
            ),
            CONSTRAINT ck_creatives_type CHECK (
                type IN ('image', 'video', 'gif')
            ),
            CONSTRAINT ck_creatives_media_source CHECK (
                stored_file_id IS NOT NULL OR external_url IS NOT NULL
            ),
            CONSTRAINT ck_creatives_status CHECK (
                status IN ('draft', 'approved', 'rejected', 'archived')
            ),
            CONSTRAINT ck_creatives_approval_state CHECK (
                approval_state IN ('pending', 'approved', 'rejected')
            ),
            CONSTRAINT fk_creatives_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_creatives_stored_file_id FOREIGN KEY (stored_file_id)
                REFERENCES stored_files (id),
            CONSTRAINT fk_creatives_content_generation_job_id FOREIGN KEY (content_generation_job_id)
                REFERENCES content_generation_jobs (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE posts (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            test_id uuid,
            product_concept_id uuid,
            product_id uuid,
            name text NOT NULL,
            slug text,
            text_content jsonb NOT NULL,
            cta_text text,
            cta_type text,
            order_channel_id uuid,
            status text NOT NULL DEFAULT 'draft',
            platform_context jsonb,
            published_url text,
            published_at timestamptz,
            created_by uuid NOT NULL,
            deleted_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_posts_status CHECK (
                status IN ('draft', 'published', 'unpublished', 'archived')
            ),
            CONSTRAINT fk_posts_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_posts_product_concept_id FOREIGN KEY (product_concept_id)
                REFERENCES product_concepts (id),
            CONSTRAINT fk_posts_product_id FOREIGN KEY (product_id)
                REFERENCES products (id),
            CONSTRAINT fk_posts_order_channel_id FOREIGN KEY (order_channel_id)
                REFERENCES order_channels (id),
            CONSTRAINT fk_posts_created_by FOREIGN KEY (created_by)
                REFERENCES users (id)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_posts_slug
        ON posts (slug)
        WHERE slug IS NOT NULL
        """
    )

    op.execute(
        """
        CREATE TABLE post_creatives (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            post_id uuid NOT NULL,
            creative_id uuid NOT NULL,
            position integer NOT NULL,
            is_primary boolean NOT NULL DEFAULT false,
            overlay_text jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_post_creatives_position CHECK (position >= 0),
            CONSTRAINT uq_post_creatives_post_id_creative_id UNIQUE (post_id, creative_id),
            CONSTRAINT uq_post_creatives_post_id_position UNIQUE (post_id, position),
            CONSTRAINT fk_post_creatives_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_post_creatives_post_id FOREIGN KEY (post_id)
                REFERENCES posts (id),
            CONSTRAINT fk_post_creatives_creative_id FOREIGN KEY (creative_id)
                REFERENCES creatives (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE creative_variants (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            creative_id uuid NOT NULL,
            stored_file_id uuid,
            external_url text,
            width integer,
            height integer,
            aspect_ratio text,
            format text,
            bitrate_kbps integer,
            duration_ms integer,
            is_primary boolean NOT NULL DEFAULT false,
            metadata jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_creative_variants_media_source CHECK (
                stored_file_id IS NOT NULL OR external_url IS NOT NULL
            ),
            CONSTRAINT fk_creative_variants_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_creative_variants_creative_id FOREIGN KEY (creative_id)
                REFERENCES creatives (id),
            CONSTRAINT fk_creative_variants_stored_file_id FOREIGN KEY (stored_file_id)
                REFERENCES stored_files (id)
        )
        """
    )

    op.execute(
        """
        CREATE INDEX ix_creatives_store_id_status
        ON creatives (store_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_posts_store_id_status
        ON posts (store_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_creative_variants_creative_id
        ON creative_variants (creative_id)
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_creatives_touch_updated_at
        BEFORE UPDATE ON creatives
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_posts_touch_updated_at
        BEFORE UPDATE ON posts
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )

    op.execute(
        """
        ALTER TABLE order_channels
        ADD CONSTRAINT fk_order_channels_post_id FOREIGN KEY (post_id)
        REFERENCES posts (id)
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE order_channels DROP CONSTRAINT IF EXISTS fk_order_channels_post_id"
    )
    op.execute("DROP TABLE IF EXISTS creative_variants")
    op.execute("DROP TABLE IF EXISTS post_creatives")
    op.execute("DROP TABLE IF EXISTS posts")
    op.execute("DROP TABLE IF EXISTS creatives")
