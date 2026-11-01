"""Email verification tokens and authentication lookup policies."""

from __future__ import annotations

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE email_verification_tokens (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            user_id uuid NOT NULL,
            email citext NOT NULL,
            token_hash char(64) NOT NULL,
            source text NOT NULL DEFAULT 'signup',
            expires_at timestamptz NOT NULL,
            used_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_email_verification_tokens_source CHECK (
                source IN ('signup', 'resend')
            ),
            CONSTRAINT uq_email_verification_tokens_hash UNIQUE (token_hash),
            CONSTRAINT fk_email_verification_tokens_user_id FOREIGN KEY (user_id)
                REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_email_verification_tokens_user_id
        ON email_verification_tokens (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_email_verification_tokens_email_created_at
        ON email_verification_tokens (email, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE POLICY p_users_auth_lookup ON users FOR SELECT
            USING (
                current_setting('app.auth_lookup', true) = 'true'
                AND deleted_at IS NULL
            )
        """
    )
    op.execute(
        """
        CREATE POLICY p_stores_auth_lookup ON stores FOR SELECT
            USING (
                current_setting('app.auth_lookup', true) = 'true'
                AND deleted_at IS NULL
            )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS p_stores_auth_lookup ON stores")
    op.execute("DROP POLICY IF EXISTS p_users_auth_lookup ON users")
    op.execute(
        "DROP INDEX IF EXISTS ix_email_verification_tokens_email_created_at"
    )
    op.execute("DROP INDEX IF EXISTS ix_email_verification_tokens_user_id")
    op.execute("DROP TABLE IF EXISTS email_verification_tokens")
