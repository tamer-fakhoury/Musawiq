"""DB-0.6 - audience and store context tables.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-25

Creates the audience taxonomy and store-context tables and adds the deferred
products.category_id FK now that categories exists. Downgrade removes the
products FK first, then drops the tables in reverse order.
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE categories (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            parent_id uuid,
            name text NOT NULL,
            slug text NOT NULL,
            is_active boolean NOT NULL DEFAULT true,
            sort_order integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_categories_slug UNIQUE (slug),
            CONSTRAINT fk_categories_parent_id FOREIGN KEY (parent_id)
                REFERENCES categories (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE niches (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            category_id uuid NOT NULL,
            store_id uuid,
            name text NOT NULL,
            slug text NOT NULL,
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_niches_category_id FOREIGN KEY (category_id)
                REFERENCES categories (id),
            CONSTRAINT fk_niches_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_niches_store_id_slug
        ON niches (store_id, slug)
        WHERE store_id IS NOT NULL
        """
    )

    op.execute(
        """
        CREATE TABLE audience_profiles (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            version integer NOT NULL,
            status text NOT NULL,
            is_current boolean NOT NULL DEFAULT false,
            niche_ids uuid[] NOT NULL DEFAULT '{}',
            languages text[] NOT NULL DEFAULT '{}',
            notes text,
            created_by uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_audience_profiles_store_id_version UNIQUE (store_id, version),
            CONSTRAINT ck_audience_profiles_status CHECK (
                status IN ('draft', 'active', 'archived')
            ),
            CONSTRAINT fk_audience_profiles_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_audience_profiles_created_by FOREIGN KEY (created_by)
                REFERENCES users (id)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_audience_profiles_store_id_current
        ON audience_profiles (store_id)
        WHERE is_current
        """
    )
    op.execute(
        """
        CREATE INDEX ix_audience_profiles_store_id_is_current
        ON audience_profiles (store_id, is_current)
        """
    )

    op.execute(
        """
        CREATE TABLE audience_segments (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            audience_profile_id uuid NOT NULL,
            label text NOT NULL,
            locations jsonb NOT NULL DEFAULT '[]'::jsonb,
            age_min integer NOT NULL,
            age_max integer NOT NULL,
            genders text[] NOT NULL DEFAULT '{}',
            interests text[] NOT NULL DEFAULT '{}',
            languages text[] NOT NULL DEFAULT '{}',
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_audience_segments_age_min CHECK (age_min >= 0),
            CONSTRAINT ck_audience_segments_age_max CHECK (age_max <= 120),
            CONSTRAINT ck_audience_segments_age_range CHECK (age_min <= age_max),
            CONSTRAINT fk_audience_segments_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_audience_segments_audience_profile_id FOREIGN KEY (audience_profile_id)
                REFERENCES audience_profiles (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_audience_segments_audience_profile_id
        ON audience_segments (audience_profile_id)
        """
    )

    op.execute(
        """
        CREATE TABLE feedback_items (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid NOT NULL,
            audience_profile_id uuid,
            source text NOT NULL,
            stored_file_id uuid,
            text text NOT NULL,
            language text,
            sentiment text,
            captured_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_feedback_items_source CHECK (source IN ('manual', 'file')),
            CONSTRAINT ck_feedback_items_sentiment CHECK (
                sentiment IN ('positive', 'neutral', 'negative')
            ),
            CONSTRAINT fk_feedback_items_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_feedback_items_audience_profile_id FOREIGN KEY (audience_profile_id)
                REFERENCES audience_profiles (id),
            CONSTRAINT fk_feedback_items_stored_file_id FOREIGN KEY (stored_file_id)
                REFERENCES stored_files (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_feedback_items_store_id_captured_at
        ON feedback_items (store_id, captured_at)
        """
    )

    op.execute(
        """
        ALTER TABLE products
        ADD CONSTRAINT fk_products_category_id FOREIGN KEY (category_id)
        REFERENCES categories (id)
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_categories_touch_updated_at
        BEFORE UPDATE ON categories
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_niches_touch_updated_at
        BEFORE UPDATE ON niches
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audience_profiles_touch_updated_at
        BEFORE UPDATE ON audience_profiles
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE products DROP CONSTRAINT IF EXISTS fk_products_category_id")
    op.execute("DROP TABLE IF EXISTS feedback_items")
    op.execute("DROP TABLE IF EXISTS audience_segments")
    op.execute("DROP TABLE IF EXISTS audience_profiles")
    op.execute("DROP TABLE IF EXISTS niches")
    op.execute("DROP TABLE IF EXISTS categories")
