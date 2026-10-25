# Roles and Privileges (DB-0.19)

Status: **definition authored, not applied.** `scripts/roles.sql` is the
executable contract for DB-0.19. The tooling stream does not execute it. Run it
as a cluster administrator on each target database after DB-0.18 has landed and
before the application is switched to these roles.

This document is the input to DB-0.15 (RLS policies). It also records the two
open ownership gaps against the current cluster.

---

## 1. Role matrix

| Capability | `musawiq_owner` | `musawiq_app` | `musawiq_reporting` | `musawiq_maintenance` |
| --- | --- | --- | --- | --- |
| `LOGIN` | yes | yes | yes | yes |
| `CONNECT` on the database | yes | yes | yes | yes |
| `USAGE` on schema `public` | yes | yes | yes | yes |
| `CREATE` on schema `public` | **yes** | no | no | no |
| Owns schema / tables / routines | **yes** | no | no | no |
| Run migrations and DDL | **yes** | no | no | no |
| `SELECT` | owner of all objects | all tables | explicit allow-list | four transient tables |
| `INSERT` | owner of all objects | all tables | no | `audit_logs` only |
| `UPDATE` | owner of all objects | all tables | no | no |
| `DELETE` | owner of all objects | all tables | no | four transient tables |
| Sequence `USAGE, SELECT` | yes (ownership) | all sequences | no | no |
| Retention / purge | no | no | no | **yes, narrow scope** |
| RLS bypass attribute | no | no | no | no |
| Elevated cluster attributes | no | no | no | no |
| Credentials | external | external | external | external |

"All tables" means every current table in `public`; the migration role's default
privileges extend the same DML grants to future tables it creates.

---

## 2. `musawiq_owner`

The migration and DDL role. It owns schema `public`, every application table,
sequence, view, and routine, and is the only role allowed to create objects.

- It runs `alembic upgrade`/`downgrade` and any schema cutover.
- It is not a runtime application role. Application connection strings must never
  use it.
- It has no elevated cluster attributes and does not bypass RLS by attribute.
  Table owners can still bypass RLS unless DB-0.15 chooses `FORCE ROW LEVEL
  SECURITY`; the owner is reserved for migrations, not tenant traffic.
- After a migration creates a table, the default privileges in `roles.sql` give
  `musawiq_app` DML on it automatically.

`roles.sql` reassigns public objects that were created by the previous migration
role (`musawiq_app`) to `musawiq_owner`. On a fresh schema this is a no-op.

---

## 3. `musawiq_app`

The runtime role. It gets:

- `CONNECT` on the database and `USAGE` on `public`;
- `SELECT, INSERT, UPDATE, DELETE` on all tables;
- `USAGE, SELECT` on all sequences.

It does **not** get:

- `CREATE` on schema `public`, or any DDL;
- ownership of the schema, tables, or routines;
- elevated cluster attributes or RLS-bypass rights;
- migration or retention responsibilities.

Two consequences of the append-only design are intentional:

- The grant on `audit_logs` allows `INSERT` so the application can write audit
  records. `trg_audit_logs_block_mutation` still rejects `UPDATE` and `DELETE`.
- The grant on `schema_migrations` is present because the task requires DML on
  all tables, but the application must not touch the migration table. A stricter
  follow-up may reduce that table to `SELECT` only.

### RLS contract

DB-0.15 owns the policies. The contract the application must implement is:

1. Every tenant-scoped transaction starts with a local setting:

   ```sql
   BEGIN;
   SET LOCAL app.store_id = '<store uuid>';
   -- tenant reads and writes
   COMMIT;
   ```

2. `SET LOCAL` is used, never a session-wide `SET`. A pooled connection must not
   leak one tenant's store id into the next request.
3. A missing or invalid `app.store_id` fails closed: the policy returns no rows
   or raises, never "all rows".
4. `musawiq_app` must not be a table owner and must not have an RLS-bypass
   attribute. It must not `SET ROLE musawiq_owner`.
5. `musawiq_maintenance` runs as a separate connection and a separate role. It is
   not the application's escape hatch.

The `NULLS NOT DISTINCT` uniqueness rules already in the schema are independent
of RLS. DB-0.15 policies must not assume that a nullable tenant key makes a row
globally unique.

---

## 4. `musawiq_reporting`

Read-only, explicit allow-list, no sequences, no default privileges:

```text
countries, currencies, languages, ad_platforms, event_types,
categories, niches, products, scoring_models,
optimization_rule_sets, decision_rule_sets
```

Explicitly excluded: `users`, `orders`, `order_items`, `audit_logs`,
`stored_files`, `feedback_items`.

Why the exclusions matter:

- `users` and `orders` carry identity and customer PII; `orders` also carries
  encrypted address payloads.
- `audit_logs` is the security record and may contain before/after payloads.
- `stored_files` exposes storage keys and file metadata.
- `feedback_items` can contain free-text customer PII.
- `order_items` is excluded because it joins directly to customer orders and
  adds no reporting value without them in the MVP.

Any new reporting table requires an explicit grant after a privacy review.
There is deliberately no default `SELECT` for this role.

---

## 5. `musawiq_maintenance`

The retention role gets only what DB-0.19a scopes:

- `SELECT, DELETE` on `import_rows`, `import_issues`, `async_jobs`,
  `stored_files`;
- `INSERT` on `audit_logs`;
- no DML on any other table, no sequences, no DDL.

Each purge run writes an `audit_logs` row with `actor_type = 'service'` and a
`schema_version` in `metadata`.

### Open gap with DB-0.23

`docs/RETENTION.md` requires more than this role currently has:

- `DELETE` on `audit_logs` after the >= 12-month window (with the audit-specific
  trigger exception);
- `DELETE` on `import_batches` after the FK guards;
- `SELECT` on `import_batches` and `orders` to evaluate those guards;
- `DELETE` on `tracking_sessions` when unreferenced;
- `DELETE` on default-partition rows (or partition DDL) for `events` and
  `metric_snapshots`;
- hard deletes or anonymisation for soft-deleted rows.

DB-0.19a deliberately implements the narrower scope requested for this task.
Before DB-0.23 is enabled, the owner must choose one of:

1. widen `musawiq_maintenance` grants to exactly the retention surface, or
2. narrow the retention job so it only touches the four transient tables and
   moves audit/partition maintenance into a separately reviewed privileged job.

Do not silently grant broader rights to the runtime role to work around this.

---

## 6. Ownership cutover and the existing cluster

`musawiq_app` already exists in this cluster with `LOGIN`, no elevated
attributes, and ownership of `musawiq` and `musawiq_test`. `scripts/roles.sql`
tolerates that:

- every `CREATE ROLE` is guarded by a `pg_roles` existence check;
- existing roles are altered only for `LOGIN`, `NOCREATEDB`, `NOCREATEROLE`, and
  `search_path`;
- no credential clause is written, so an existing authentication setup is not
  overwritten.

What the script does change on the target database:

- `public` schema ownership moves to `musawiq_owner`;
- public objects owned by `musawiq_app` move to `musawiq_owner`;
- `CREATE` on `public` is removed from `PUBLIC` and from every runtime role;
- runtime grants are rebuilt from the matrix above.

What it deliberately does **not** change:

- **Database ownership.** `musawiq_app` owns both databases. A database owner
  keeps database-level powers (for example creating new schemas) even after
  losing schema and object ownership. Full least privilege therefore needs a
  separate, owner-approved cutover:

  ```sql
  ALTER DATABASE musawiq OWNER TO musawiq_owner;
  ALTER DATABASE musawiq_test OWNER TO musawiq_owner;
  ```

  Run those while connected to another database. Depending on the server, the
  new owner may need `CREATEDB` temporarily; `musawiq_owner` is defined as
  `NOCREATEDB`, so the cluster administrator decides and reverts that grant.

- **The migration connection.** `MUSAWIQ_DATABASE_URL` currently uses
  `musawiq_app`. Once `CREATE` on `public` is removed, migrations that still use
  the app role fail. Switch the migration URL to `musawiq_owner` in the same
  coordinated change. This task does not edit `.env` or `migrations/`.

- **Scratch databases.** `scripts/verify_db.py` creates scratch databases owned
  by `musawiq_app` and runs migrations there as the app URL. `roles.sql` is not
  applied to those scratch databases, so the local verification pipeline keeps
  working after the cutover. The owner should make an explicit decision before
  running `roles.sql` inside a scratch database.

### Ordering

1. Apply migrations through DB-0.18.
2. Confirm the reporting allow-list tables exist (`scoring_models`,
   `optimization_rule_sets`, `decision_rule_sets` are created by later DB tasks).
3. Run `scripts/roles.sql` as a cluster administrator on each target database.
4. Move database ownership to `musawiq_owner` (separate step).
5. Switch `MUSAWIQ_DATABASE_URL` for migrations to `musawiq_owner`.
6. Keep `musawiq_app` for runtime DML only.

If a reporting allow-list table is missing, the whole `roles.sql` transaction
rolls back. That is intentional: a partial role cutover is worse than a clean
failure.

---

## 7. Credentials and connection security

- No credentials belong in this repository. `scripts/roles.sql` contains no
  credential clauses at all.
- Authentication is provisioned out-of-band (scram secret store, pgpass, or the
  platform identity provider).
- Connections must use TLS in deployed environments. The role definition does
  not weaken any TLS requirement.
- Review `pg_roles` for unexpected attributes before enabling traffic. The
  script assumes existing roles have no elevated attributes; it does not grant
  any.

---

## 8. Verification

Static checks (no database execution):

```powershell
.venv\Scripts\python.exe -m pytest tests/tools/test_roles_sql.py -q
```

Post-cutover checks, to be run by the owner:

- every role exists, and none has elevated cluster attributes;
- `has_schema_privilege('musawiq_app', 'public', 'CREATE')` is false;
- `has_database_privilege(..., 'CONNECT')` is true for all four roles;
- `musawiq_reporting` has `SELECT` only on the allow-list and no sequence
  privilege;
- `musawiq_maintenance` has only the four transient-table grants plus
  `INSERT` on `audit_logs`;
- `SET ROLE musawiq_app; CREATE TABLE public.role_probe (id int);` fails;
- a reporting `SELECT` against `users`/`orders` fails;
- the RLS tenant test from DB-0.15 passes as `musawiq_app`.

---

## 9. Non-goals

- RLS policy bodies, `FORCE ROW LEVEL SECURITY`, and policy tests (DB-0.15).
- Password/credential rotation and TLS configuration.
- The actual role cutover or database ownership transfer (owner action).
- Changing `.env`, `migrations/`, or the migration chain.
