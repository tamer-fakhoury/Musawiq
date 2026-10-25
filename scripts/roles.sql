-- Musawiq database roles and privileges (DB-0.19).
--
-- Authoring artifact: the tooling stream does not execute this file.
--
-- Run as a cluster administrator on each target database after the DB-0.18
-- migrations have landed. The whole file is one transaction: if an expected
-- reporting table is missing, every change rolls back.
--
-- Credentials are provisioned out-of-band (pgpass, a scram secret store, or the
-- platform identity provider). This file intentionally contains no credential
-- clauses and no plaintext secrets.
--
-- Order matters:
--   1. create roles (guarded, so existing roles are preserved);
--   2. set baseline role attributes and search_path;
--   3. hand schema and object ownership to musawiq_owner;
--   4. remove accidental grants and apply the least-privilege matrix.
--
-- musawiq_app already exists in the current cluster and owns the musawiq and
-- musawiq_test databases. The guards below tolerate that. Database ownership is
-- not changed here; see the cutover note at the end.

BEGIN;

-- 1. Roles -----------------------------------------------------------------
-- musawiq_owner: migration and DDL role. It owns the public schema and every
-- application object; it is never used for runtime application traffic.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'musawiq_owner') THEN
        CREATE ROLE musawiq_owner LOGIN NOCREATEDB NOCREATEROLE;
    END IF;
END
$$;

-- musawiq_app: runtime DML only. No object ownership and no CREATE on public.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'musawiq_app') THEN
        CREATE ROLE musawiq_app LOGIN NOCREATEDB NOCREATEROLE;
    END IF;
END
$$;

-- musawiq_reporting: read-only, explicit non-PII allow-list.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'musawiq_reporting') THEN
        CREATE ROLE musawiq_reporting LOGIN NOCREATEDB NOCREATEROLE;
    END IF;
END
$$;

-- musawiq_maintenance: retention jobs only.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'musawiq_maintenance') THEN
        CREATE ROLE musawiq_maintenance LOGIN NOCREATEDB NOCREATEROLE;
    END IF;
END
$$;

-- Make the attributes explicit for roles that may already exist. Roles are
-- created without elevated attributes; none is granted here. Existing elevated
-- attributes must be reviewed by the cluster administrator before this script
-- is used for traffic.
ALTER ROLE musawiq_owner WITH LOGIN NOCREATEDB NOCREATEROLE;
ALTER ROLE musawiq_app WITH LOGIN NOCREATEDB NOCREATEROLE;
ALTER ROLE musawiq_reporting WITH LOGIN NOCREATEDB NOCREATEROLE;
ALTER ROLE musawiq_maintenance WITH LOGIN NOCREATEDB NOCREATEROLE;

-- Pin the search path so a role cannot resolve objects through a personal
-- schema. pg_catalog is still searched implicitly before public.
ALTER ROLE musawiq_owner SET search_path = public;
ALTER ROLE musawiq_app SET search_path = public;
ALTER ROLE musawiq_reporting SET search_path = public;
ALTER ROLE musawiq_maintenance SET search_path = public;

-- 2. Database connection ---------------------------------------------------
-- CONNECT is granted on the database this script is run against. Run the file
-- once per target database (for example musawiq and musawiq_test).
DO $$
BEGIN
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO '
        'musawiq_owner, musawiq_app, musawiq_reporting, musawiq_maintenance',
        current_database()
    );
END
$$;

-- 3. Schema ownership and hardening ---------------------------------------
-- Only musawiq_owner may create objects in public. The previous migration role
-- was musawiq_app (it still owns the two databases); moving the schema and
-- objects here is the ownership cutover for the schema layer.
ALTER SCHEMA public OWNER TO musawiq_owner;
GRANT USAGE, CREATE ON SCHEMA public TO musawiq_owner;

-- No runtime role may create objects in public.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL PRIVILEGES ON SCHEMA public
    FROM musawiq_app, musawiq_reporting, musawiq_maintenance;
GRANT USAGE ON SCHEMA public
    TO musawiq_app, musawiq_reporting, musawiq_maintenance;

-- Existing objects were created by the previous migration role. Reassign table,
-- sequence, view, and routine ownership to musawiq_owner, excluding extension
-- members (their ownership follows the extension). This is idempotent: after
-- the first run there is nothing left owned by musawiq_app.
DO $$
DECLARE
    obj record;
    object_type text;
BEGIN
    FOR obj IN
        SELECT c.relname, c.relkind
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relowner = 'musawiq_app'::regrole
          AND c.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')
          AND NOT EXISTS (
              SELECT 1
              FROM pg_depend d
              WHERE d.classid = 'pg_class'::regclass
                AND d.objid = c.oid
                AND d.deptype = 'e'
          )
        ORDER BY c.relname
    LOOP
        object_type := CASE obj.relkind
            WHEN 'S' THEN 'SEQUENCE'
            WHEN 'v' THEN 'VIEW'
            WHEN 'm' THEN 'MATERIALIZED VIEW'
            WHEN 'f' THEN 'FOREIGN TABLE'
            ELSE 'TABLE'
        END;
        EXECUTE format(
            'ALTER %s public.%I OWNER TO musawiq_owner',
            object_type,
            obj.relname
        );
    END LOOP;
END
$$;

DO $$
DECLARE
    obj record;
BEGIN
    FOR obj IN
        SELECT p.oid
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND p.proowner = 'musawiq_app'::regrole
          AND NOT EXISTS (
              SELECT 1
              FROM pg_depend d
              WHERE d.classid = 'pg_proc'::regclass
                AND d.objid = p.oid
                AND d.deptype = 'e'
          )
        ORDER BY p.proname, p.oid
    LOOP
        EXECUTE format(
            'ALTER ROUTINE %s OWNER TO musawiq_owner',
            obj.oid::regprocedure
        );
    END LOOP;
END
$$;

-- Extensions are library objects, not application schema objects, and are not
-- reassigned here. Their owner is intentionally left to the cluster
-- administrator's extension-management process.

-- 4. Runtime application role ---------------------------------------------
-- Direct DML on every current table; no DDL, no ownership.
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM musawiq_app;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM musawiq_app;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public
    TO musawiq_app;
GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA public
    TO musawiq_app;

-- Future objects created by the migration role inherit the runtime grants.
-- There is intentionally no default CREATE or ownership for musawiq_app.
ALTER DEFAULT PRIVILEGES FOR ROLE musawiq_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO musawiq_app;
ALTER DEFAULT PRIVILEGES FOR ROLE musawiq_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO musawiq_app;

-- 5. Reporting role: read-only allow-list ----------------------------------
-- The allow-list is deliberately explicit. Add a table here only after a
-- privacy review. Reporting gets no sequence access and no default privileges.
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM musawiq_reporting;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM musawiq_reporting;

GRANT SELECT ON TABLE
    public.countries,
    public.currencies,
    public.languages,
    public.ad_platforms,
    public.event_types,
    public.categories,
    public.niches,
    public.products,
    public.scoring_models,
    public.optimization_rule_sets,
    public.decision_rule_sets
TO musawiq_reporting;

-- Explicitly deny the sensitive tables. This is redundant with the allow-list
-- but keeps the negative contract in one visible place.
REVOKE ALL PRIVILEGES ON TABLE
    public.users,
    public.orders,
    public.order_items,
    public.audit_logs,
    public.stored_files,
    public.feedback_items
FROM musawiq_reporting;

-- 6. Maintenance role: retention and purge only ----------------------------
-- The current DB-0.19a scope is intentionally narrow. See docs/RETENTION.md for
-- the wider operations DB-0.23 needs; that gap must be resolved before the
-- retention job is enabled.
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM musawiq_maintenance;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM musawiq_maintenance;

GRANT SELECT, DELETE ON TABLE
    public.import_rows,
    public.import_issues,
    public.async_jobs,
    public.stored_files
TO musawiq_maintenance;

-- Purge runs append their own audit record, and nothing else.
GRANT INSERT ON TABLE public.audit_logs TO musawiq_maintenance;

COMMIT;

-- Cutover note: musawiq_app still owns the musawiq and musawiq_test databases
-- in the current cluster. Database ownership is a shared object and is
-- deliberately not changed by this per-database script. Complete the cutover
-- separately:
--   1. switch the migration connection to musawiq_owner;
--   2. run, in each database, ALTER DATABASE <database> OWNER TO musawiq_owner
--      (a cluster administrator may need to grant CREATEDB to musawiq_owner
--      temporarily if the server requires it for ownership transfer);
--   3. keep musawiq_app for runtime DML only.
