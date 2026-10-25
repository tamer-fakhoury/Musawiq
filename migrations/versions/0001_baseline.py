"""Migration tooling baseline.

Revision ID: 0001
Revises: None
Create Date: 2026-10-25

Establishes the revision chain only. This revision creates no tables,
extensions, or functions; every subsequent DB task adds one migration on top
of this baseline.

Every revision must implement both upgrade() and downgrade(). Write explicit
SQL with op.execute(); do not rely on autogenerate.
"""

from __future__ import annotations

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
