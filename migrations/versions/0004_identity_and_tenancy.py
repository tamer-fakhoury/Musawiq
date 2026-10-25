"""DB-0.4 - identity and tenancy tables.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25

Creates users, stores, audit_logs, and async_jobs in FK dependency order,
adds the uniqueness constraints, and attaches the shared touch/append-only
triggers from DB-0.2. Downgrade drops the tables in reverse dependency order.
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE users (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            email citext NOT NULL,
            password_hash text,
            full_name text NOT NULL,
            phone text,
            locale text,
            timezone text,
            role text NOT NULL,
            status text NOT NULL,
            email_verified_at timestamptz,
            last_login_at timestamptz,
            auth_provider text,
            auth_subject text,
            deleted_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_users_email UNIQUE (email),
            CONSTRAINT ck_users_role CHECK (role IN ('owner', 'manager', 'analyst')),
            CONSTRAINT ck_users_status CHECK (status IN ('invited', 'active', 'disabled'))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_users_auth_provider_auth_subject
        ON users (auth_provider, auth_subject)
        WHERE auth_provider IS NOT NULL AND auth_subject IS NOT NULL
        """
    )

    op.execute(
        """
        CREATE TABLE stores (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            owner_user_id uuid NOT NULL,
            name text NOT NULL,
            slug text NOT NULL,
            status text NOT NULL,
            default_currency char(3) NOT NULL,
            default_language text NOT NULL,
            timezone text NOT NULL,
            country_code char(2) NOT NULL,
            onboarding_status text NOT NULL,
            settings jsonb NOT NULL DEFAULT '{}'::jsonb,
            deleted_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_stores_owner_user_id UNIQUE (owner_user_id),
            CONSTRAINT uq_stores_slug UNIQUE (slug),
            CONSTRAINT ck_stores_status CHECK (status IN ('active', 'suspended', 'closed')),
            CONSTRAINT ck_stores_onboarding_status CHECK (
                onboarding_status IN ('not_started', 'in_progress', 'completed')
            ),
            CONSTRAINT fk_stores_owner_user_id FOREIGN KEY (owner_user_id)
                REFERENCES users (id),
            CONSTRAINT fk_stores_default_currency FOREIGN KEY (default_currency)
                REFERENCES currencies (code),
            CONSTRAINT fk_stores_default_language FOREIGN KEY (default_language)
                REFERENCES languages (code),
            CONSTRAINT fk_stores_country_code FOREIGN KEY (country_code)
                REFERENCES countries (code)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE audit_logs (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid,
            actor_user_id uuid,
            actor_type text NOT NULL,
            action text NOT NULL,
            target_type text NOT NULL,
            target_id uuid,
            before jsonb,
            after jsonb,
            metadata jsonb,
            ip_hash char(64),
            user_agent text,
            correlation_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_audit_logs_actor_type CHECK (
                actor_type IN ('user', 'system', 'service')
            ),
            CONSTRAINT fk_audit_logs_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id),
            CONSTRAINT fk_audit_logs_actor_user_id FOREIGN KEY (actor_user_id)
                REFERENCES users (id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE async_jobs (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            store_id uuid,
            job_type text NOT NULL,
            state text NOT NULL,
            idempotency_key text,
            payload jsonb,
            result jsonb,
            progress_current integer NOT NULL DEFAULT 0,
            progress_total integer,
            attempt_count integer NOT NULL DEFAULT 0,
            max_attempts integer NOT NULL DEFAULT 3,
            error_code text,
            error_message text,
            correlation_id uuid,
            scheduled_at timestamptz,
            started_at timestamptz,
            finished_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_async_jobs_job_type CHECK (
                job_type IN (
                    'import',
                    'integration_sync',
                    'page_generation',
                    'ad_publication',
                    'metric_sync',
                    'recommendation_generation',
                    'content_generation'
                )
            ),
            CONSTRAINT ck_async_jobs_state CHECK (
                state IN ('queued', 'running', 'succeeded', 'failed', 'partial', 'cancelled')
            ),
            CONSTRAINT fk_async_jobs_store_id FOREIGN KEY (store_id)
                REFERENCES stores (id)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_async_jobs_idempotency_key
        ON async_jobs (idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_users_touch_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_stores_touch_updated_at
        BEFORE UPDATE ON stores
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_async_jobs_touch_updated_at
        BEFORE UPDATE ON async_jobs
        FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_block_mutation
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION fn_block_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS async_jobs")
    op.execute("DROP TABLE IF EXISTS audit_logs")
    op.execute("DROP TABLE IF EXISTS stores")
    op.execute("DROP TABLE IF EXISTS users")
