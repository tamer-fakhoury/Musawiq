"""DB-0.15 - row-level security with forced policies.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-25

Enables and forces RLS on every tenant table, on the store root, and on users.
Tenant tables use app.store_id; stores uses its own id; users uses app.user_id.
Users are intentionally self-only: multi-user listing is a Phase 1 concern.
Reference tables without store_id are left without RLS. Downgrade drops every
policy and disables RLS on the tables this revision touched.
"""

from __future__ import annotations

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            t record;
        BEGIN
            FOR t IN
                SELECT c.table_name
                FROM information_schema.columns c
                JOIN information_schema.tables tbl
                  ON tbl.table_schema = c.table_schema
                 AND tbl.table_name = c.table_name
                WHERE c.table_schema = 'public'
                  AND tbl.table_type = 'BASE TABLE'
                  AND c.column_name = 'store_id'
                  AND c.is_nullable = 'NO'
                ORDER BY c.table_name
            LOOP
                EXECUTE format(
                    'ALTER TABLE %I ENABLE ROW LEVEL SECURITY',
                    t.table_name
                );
                EXECUTE format(
                    'ALTER TABLE %I FORCE ROW LEVEL SECURITY',
                    t.table_name
                );
                EXECUTE format(
                    'CREATE POLICY %I ON %I FOR ALL '
                    'USING (store_id = nullif(current_setting(''app.store_id'', true), '''')::uuid) '
                    'WITH CHECK (store_id = nullif(current_setting(''app.store_id'', true), '''')::uuid)',
                    'p_' || t.table_name || '_tenant',
                    t.table_name
                );
            END LOOP;
        END
        $$;
        """
    )

    op.execute(
        """
        DO $$
        DECLARE
            t record;
        BEGIN
            FOR t IN
                SELECT unnest(ARRAY[
                    'content_providers',
                    'niches',
                    'scoring_models',
                    'optimization_rule_sets',
                    'decision_rule_sets',
                    'async_jobs',
                    'audit_logs'
                ]) AS table_name
            LOOP
                EXECUTE format(
                    'ALTER TABLE %I ENABLE ROW LEVEL SECURITY',
                    t.table_name
                );
                EXECUTE format(
                    'ALTER TABLE %I FORCE ROW LEVEL SECURITY',
                    t.table_name
                );
                EXECUTE format(
                    'CREATE POLICY %I ON %I FOR SELECT '
                    'USING (store_id IS NULL OR store_id = nullif(current_setting(''app.store_id'', true), '''')::uuid)',
                    'p_' || t.table_name || '_read',
                    t.table_name
                );
                EXECUTE format(
                    'CREATE POLICY %I ON %I FOR ALL '
                    'USING (store_id = nullif(current_setting(''app.store_id'', true), '''')::uuid) '
                    'WITH CHECK (store_id = nullif(current_setting(''app.store_id'', true), '''')::uuid)',
                    'p_' || t.table_name || '_tenant',
                    t.table_name
                );
            END LOOP;
        END
        $$;
        """
    )

    op.execute(
        """
        ALTER TABLE stores ENABLE ROW LEVEL SECURITY;
        ALTER TABLE stores FORCE ROW LEVEL SECURITY;
        CREATE POLICY p_stores_tenant ON stores FOR ALL
            USING (id = nullif(current_setting('app.store_id', true), '')::uuid)
            WITH CHECK (id = nullif(current_setting('app.store_id', true), '')::uuid);
        """
    )
    op.execute(
        """
        ALTER TABLE users ENABLE ROW LEVEL SECURITY;
        ALTER TABLE users FORCE ROW LEVEL SECURITY;
        CREATE POLICY p_users_self ON users FOR ALL
            USING (id = nullif(current_setting('app.user_id', true), '')::uuid)
            WITH CHECK (id = nullif(current_setting('app.user_id', true), '')::uuid);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            t record;
        BEGIN
            FOR t IN
                SELECT c.table_name
                FROM information_schema.columns c
                JOIN information_schema.tables tbl
                  ON tbl.table_schema = c.table_schema
                 AND tbl.table_name = c.table_name
                WHERE c.table_schema = 'public'
                  AND tbl.table_type = 'BASE TABLE'
                  AND c.column_name = 'store_id'
                  AND c.is_nullable = 'NO'
                ORDER BY c.table_name
            LOOP
                EXECUTE format(
                    'DROP POLICY IF EXISTS %I ON %I',
                    'p_' || t.table_name || '_tenant',
                    t.table_name
                );
                EXECUTE format(
                    'ALTER TABLE %I NO FORCE ROW LEVEL SECURITY',
                    t.table_name
                );
                EXECUTE format(
                    'ALTER TABLE %I DISABLE ROW LEVEL SECURITY',
                    t.table_name
                );
            END LOOP;
        END
        $$;
        """
    )

    op.execute(
        """
        DO $$
        DECLARE
            t record;
        BEGIN
            FOR t IN
                SELECT unnest(ARRAY[
                    'content_providers',
                    'niches',
                    'scoring_models',
                    'optimization_rule_sets',
                    'decision_rule_sets',
                    'async_jobs',
                    'audit_logs'
                ]) AS table_name
            LOOP
                EXECUTE format(
                    'DROP POLICY IF EXISTS %I ON %I',
                    'p_' || t.table_name || '_read',
                    t.table_name
                );
                EXECUTE format(
                    'DROP POLICY IF EXISTS %I ON %I',
                    'p_' || t.table_name || '_tenant',
                    t.table_name
                );
                EXECUTE format(
                    'ALTER TABLE %I NO FORCE ROW LEVEL SECURITY',
                    t.table_name
                );
                EXECUTE format(
                    'ALTER TABLE %I DISABLE ROW LEVEL SECURITY',
                    t.table_name
                );
            END LOOP;
        END
        $$;
        """
    )

    op.execute(
        """
        DROP POLICY IF EXISTS p_users_self ON users;
        ALTER TABLE users NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE users DISABLE ROW LEVEL SECURITY;
        """
    )
    op.execute(
        """
        DROP POLICY IF EXISTS p_stores_tenant ON stores;
        ALTER TABLE stores NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE stores DISABLE ROW LEVEL SECURITY;
        """
    )
