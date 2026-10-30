"""Public read access for published landing pages (FR-3.1.5).

Published pages are served by an unauthenticated route. Row-level security is
still enforced, so this revision adds read-only policies that expose exactly the
published rows:

* ``landing_pages`` rows whose ``status`` is ``published``.
* ``page_versions`` rows belonging to a published landing page.

No write access is granted by these policies and unpublished pages remain
invisible to the tenant policies as before.
"""

from __future__ import annotations

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE POLICY p_landing_pages_public_read ON landing_pages
            FOR SELECT
            USING (status = 'published')
        """
    )
    op.execute(
        """
        CREATE POLICY p_page_versions_public_read ON page_versions
            FOR SELECT
            USING (
                EXISTS (
                    SELECT 1 FROM landing_pages
                    WHERE landing_pages.id = page_versions.landing_page_id
                      AND landing_pages.status = 'published'
                )
            )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS p_page_versions_public_read ON page_versions")
    op.execute("DROP POLICY IF EXISTS p_landing_pages_public_read ON landing_pages")
