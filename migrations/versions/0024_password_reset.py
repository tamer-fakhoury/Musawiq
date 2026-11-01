"""Password reset purpose and session invalidation (FR-0.6.5)."""

from __future__ import annotations

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN password_changed_at timestamptz"
    )
    op.execute(
        """
        ALTER TABLE email_verification_tokens
        DROP CONSTRAINT ck_email_verification_tokens_source
        """
    )
    op.execute(
        """
        ALTER TABLE email_verification_tokens
        ADD CONSTRAINT ck_email_verification_tokens_source CHECK (
            source IN ('signup', 'resend', 'password_reset')
        )
        """
    )
    op.execute(
        """
        ALTER TABLE email_verification_tokens
        ADD COLUMN purpose text NOT NULL DEFAULT 'email_verification'
        """
    )
    op.execute(
        """
        ALTER TABLE email_verification_tokens
        ADD CONSTRAINT ck_email_verification_tokens_purpose CHECK (
            purpose IN ('email_verification', 'password_reset')
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE email_verification_tokens "
        "DROP CONSTRAINT IF EXISTS ck_email_verification_tokens_purpose"
    )
    op.execute(
        "ALTER TABLE email_verification_tokens DROP COLUMN IF EXISTS purpose"
    )
    op.execute(
        "ALTER TABLE email_verification_tokens "
        "DROP CONSTRAINT ck_email_verification_tokens_source"
    )
    op.execute(
        """
        ALTER TABLE email_verification_tokens
        ADD CONSTRAINT ck_email_verification_tokens_source CHECK (
            source IN ('signup', 'resend')
        )
        """
    )
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_changed_at")
