# Retention and Purge Plan (DB-0.23)

Status: **plan only** — no purge job is installed by a migration yet. This
document defines the windows, the FK-safe order, the batching/idempotency rules,
and the audit record every run must write. It is the contract DB-0.23 and the
DB-0.19 roles implement.

Retention is a maintenance-role concern. Application roles never delete
retained data, and retention never uses `ON DELETE CASCADE`.

---

## 1. Windows by table class

All defaults are UTC. Every window is configurable through the maintenance
process environment; the audit window has a hard floor.

| Table class | Default window | Config key | Starts from | Method |
| --- | --- | --- | --- | --- |
| `audit_logs` | **12 months (minimum)** | `MUSAWIQ_RETENTION_AUDIT_MONTHS` | `created_at` | Batched `DELETE`; never before the window |
| `events` | 12 months | `MUSAWIQ_RETENTION_EVENTS_MONTHS` | `occurred_at` | Drop whole monthly partitions; delete default-partition rows in batches |
| `tracking_sessions` | 12 months | `MUSAWIQ_RETENTION_SESSIONS_MONTHS` | `started_at` | Batched `DELETE`, only when unreferenced |
| `metric_snapshots` | 24 months | `MUSAWIQ_RETENTION_METRICS_MONTHS` | `period_start` | Drop whole monthly partitions |
| `import_rows` | 0 days after commit | `MUSAWIQ_RETENTION_IMPORT_STAGING_DAYS` | `completed_at` / `updated_at` | Batched `DELETE` |
| `import_issues` | 0 days after commit | `MUSAWIQ_RETENTION_IMPORT_STAGING_DAYS` | `completed_at` / `updated_at` | Batched `DELETE` |
| `import_batches` | 90 days for failed/cancelled; completed retained as history | `MUSAWIQ_RETENTION_IMPORT_BATCH_DAYS` | `completed_at` / `updated_at` | Batched `DELETE` with reference guards |
| `stored_files` (staged, no batch) | 7 days | `MUSAWIQ_RETENTION_STAGED_FILE_DAYS` | `created_at` | Delete object, then row |
| Soft-deleted rows (`deleted_at`) | 30 days | `MUSAWIQ_RETENTION_SOFT_DELETE_DAYS` | `deleted_at` | Batched hard delete or anonymisation |
| `stored_files` already `deleted` | 30 days after `deleted_at` | `MUSAWIQ_RETENTION_SOFT_DELETE_DAYS` | `deleted_at` | Delete object (if still present), then row |

Rules that override the table:

- **`audit_logs` is append-only and is never purged before its window.** The
  configured window must be `>= 12` months; the runner aborts if it is not.
  Audit rows are never updated. Appending a new audit row is always allowed.
- **Consent and legal hold win.** A session with `consent_state = 'denied'` may
  be purged earlier only if the product/consent policy permits it. Rows under a
  legal hold are skipped regardless of age.
- **Import staging is transient.** `import_rows` and `import_issues` become
  eligible immediately after the batch commits (`status = 'completed'`) or is
  cancelled/failed. The default grace is 0 days; a small grace (for example 7
  days) may be configured so previews and error reports remain available.
- **`import_batches` is history.** Completed batches are retained as import
  history (counters and the error-report link are product-visible), so the
  default job does not delete them. Only failed/cancelled/abandoned batches are
  eligible after the configured window, and only with no remaining staging rows
  and no orders referencing the batch.
- **Staged files with no batch** are only eligible when `status = 'staged'`,
  `purpose = 'sales_csv'`, and no `import_batches` row references the file as
  `stored_file_id` or `error_report_file_id`. Other staged purposes are the
  responsibility of their owning flow.
- **A session window must not be shorter than the event window** while
  `events.tracking_session_id` uses a restricting FK. Purge events first, then
  sessions. `orders.tracking_session_id` (FK added in DB-0.13) is a second
  guard: a session referenced by an order is retained.
- **Partition drops replace row deletes for `events` and `metric_snapshots`.**
  `DROP TABLE` is DDL and does not fire append-only triggers.

---

## 2. Purge order

Retention is a dependency-ordered pipeline. Never start a later step while an
earlier step still has eligible rows.

### 2.1 Import staging and batches

FK reasons:

- `import_issues.import_row_id -> import_rows(id)`
- `import_issues.import_batch_id -> import_batches(id)`
- `import_rows.import_batch_id -> import_batches(id)`
- `import_rows.created_order_id -> orders(id)` (outbound from staging)
- `orders.import_batch_id -> import_batches(id)` (blocks batch deletion)

Exact order:

1. **`import_issues`**
2. **`import_rows`**
3. **`import_batches`** (only if no issues, rows, or orders reference the batch)

Batched delete pattern (repeat until the statement affects 0 rows):

```sql
BEGIN;
SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '2s';

WITH victims AS (
    SELECT i.ctid
    FROM public.import_issues i
    JOIN public.import_batches b ON b.id = i.import_batch_id
    WHERE COALESCE(b.completed_at, b.updated_at)
              < now() - make_interval(days => :grace_days)
      AND b.status IN ('completed', 'cancelled', 'failed')
    ORDER BY i.ctid
    LIMIT :batch_size
)
DELETE FROM public.import_issues i
USING victims v
WHERE i.ctid = v.ctid;

COMMIT;
```

```sql
BEGIN;
SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '2s';

WITH victims AS (
    SELECT r.ctid
    FROM public.import_rows r
    JOIN public.import_batches b ON b.id = r.import_batch_id
    WHERE COALESCE(b.completed_at, b.updated_at)
              < now() - make_interval(days => :grace_days)
      AND b.status IN ('completed', 'cancelled', 'failed')
      AND NOT EXISTS (
          SELECT 1 FROM public.import_issues i WHERE i.import_row_id = r.id
      )
    ORDER BY r.ctid
    LIMIT :batch_size
)
DELETE FROM public.import_rows r
USING victims v
WHERE r.ctid = v.ctid;

COMMIT;
```

```sql
BEGIN;
SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '2s';

DELETE FROM public.import_batches b
WHERE b.id IN (
    SELECT b2.id
    FROM public.import_batches b2
    WHERE COALESCE(b2.completed_at, b2.updated_at)
              < now() - make_interval(days => :batch_days)
      AND b2.status IN ('cancelled', 'failed')
      AND NOT EXISTS (
          SELECT 1 FROM public.import_rows r WHERE r.import_batch_id = b2.id
      )
      AND NOT EXISTS (
          SELECT 1 FROM public.import_issues i WHERE i.import_batch_id = b2.id
      )
      AND NOT EXISTS (
          SELECT 1 FROM public.orders o WHERE o.import_batch_id = b2.id
      )
    LIMIT :batch_size
);

COMMIT;
```

Completed batches are deliberately excluded from the last statement by default.
If the owner wants completed batches removed, the FK
`fk_orders_import_batch_id` must first become `ON DELETE SET NULL` (or the
provenance must be copied), otherwise the delete fails. This is a specification
conflict; see section 8.

### 2.2 Staged files with no batch

Delete the storage object first; only delete the row after the object deletion
succeeds. Both steps are idempotent.

```sql
WITH candidates AS (
    SELECT f.id, f.storage_provider, f.storage_key
    FROM public.stored_files f
    WHERE f.purpose = 'sales_csv'
      AND f.status = 'staged'
      AND f.deleted_at IS NULL
      AND f.created_at < now() - make_interval(days => :staged_days)
      AND NOT EXISTS (
          SELECT 1 FROM public.import_batches b
          WHERE b.stored_file_id = f.id OR b.error_report_file_id = f.id
      )
    ORDER BY f.created_at
    LIMIT :batch_size
)
SELECT * FROM candidates;
```

For each candidate: delete `storage_key` through the storage adapter, then:

```sql
DELETE FROM public.stored_files
WHERE id = :file_id
  AND status = 'staged'
  AND deleted_at IS NULL;
```

Before enabling the generic form, include every other table that can reference
`stored_files` (`products.image_file_id`, `feedback_items.stored_file_id`,
`creatives.stored_file_id`, `creative_variants.stored_file_id`,
`deposits.evidence_file_id`, and the `uuid[]` columns `page_versions.image_file_ids`
and `content_generation_jobs.result_creative_ids`). For `sales_csv` the batch
guard is the only expected reference, but the guard must be exhaustive for any
purpose you add to this job.

### 2.3 `events` and `tracking_sessions`

Events are partitioned by `occurred_at` (see `docs/PARTITIONING.md`). Drop
monthly partitions older than the cutoff; delete old rows in the default
partition in batches only if it is non-empty.

```sql
-- Only for partitions whose upper bound is strictly before the cutoff.
ALTER TABLE public.events DETACH PARTITION public.events_2025_01;
DROP TABLE public.events_2025_01;
```

Then delete unreferenced sessions:

```sql
BEGIN;
SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '2s';

WITH victims AS (
    SELECT s.ctid
    FROM public.tracking_sessions s
    WHERE s.started_at < now() - make_interval(months => :session_months)
      AND NOT EXISTS (
          SELECT 1 FROM public.events e WHERE e.tracking_session_id = s.id
      )
      AND NOT EXISTS (
          SELECT 1 FROM public.orders o WHERE o.tracking_session_id = s.id
      )
    ORDER BY s.started_at
    LIMIT :batch_size
)
DELETE FROM public.tracking_sessions s
USING victims v
WHERE s.ctid = v.ctid;

COMMIT;
```

If sessions are retained longer than events, the `NOT EXISTS` on `events` is
redundant but harmless. If they are purged first, the FK rejects the delete; the
correct fix is to raise the session window, not to cascade.

### 2.4 `metric_snapshots`

Drop monthly partitions whose upper bound is before
`now() - make_interval(months => :metrics_months)`. No inbound FK references
`metric_snapshots` (`test_result_snapshots.source_metric_snapshot_ids` is a
`uuid[]`), so a partition drop is safe once the partition is out of window.

### 2.5 `audit_logs` (last)

Audit rows are purged only after the window, in bounded batches, and only with
the maintenance trigger exception described in section 3:

```sql
BEGIN;
SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '2s';

DELETE FROM public.audit_logs
WHERE id IN (
    SELECT id
    FROM public.audit_logs
    WHERE created_at < now() - make_interval(months => :audit_months)
      AND COALESCE(metadata ->> 'legal_hold', 'false') <> 'true'
    LIMIT :batch_size
);

COMMIT;
```

`created_at < now() - 12 months` is the earliest possible deletion; a larger
window is safer. Nothing in the pipeline may delete audit rows with a cutoff
younger than 12 months.

---

## 3. The append-only trigger blocker

`audit_logs` has `trg_audit_logs_block_mutation`, which raises on every
`UPDATE` **and `DELETE`** (DB-0.4). Retention must therefore be wired in one of
these ways before DB-0.23 can purge audit rows:

1. **Preferred — audit-specific trigger exception in DB-0.19.** Leave the shared
   `fn_block_mutation()` untouched for the other append-only tables and give
   `audit_logs` its own function, so only the maintenance role can delete, and
   only inside a retention transaction:

   ```sql
   CREATE OR REPLACE FUNCTION public.fn_block_audit_mutation()
   RETURNS trigger
   LANGUAGE plpgsql
   AS $$
   BEGIN
       IF TG_OP = 'DELETE'
          AND current_user = 'musawiq_maintenance'
          AND current_setting('app.retention_purge', true) = 'on' THEN
           RETURN OLD;
       END IF;
       RAISE EXCEPTION 'append-only table %: % is not allowed',
           TG_TABLE_NAME, TG_OP;
       RETURN OLD;
   END;
   $$;

   DROP TRIGGER trg_audit_logs_block_mutation ON public.audit_logs;
   CREATE TRIGGER trg_audit_logs_block_mutation
       BEFORE UPDATE OR DELETE ON public.audit_logs
       FOR EACH ROW EXECUTE FUNCTION public.fn_block_audit_mutation();
   ```

   The purge runner sets `SET LOCAL app.retention_purge = 'on'` inside the
   batch transaction. `UPDATE` remains blocked for every role, and every other
   append-only table keeps the original function.

2. **Fallback — temporary trigger disable.** Run as the table owner in the
   maintenance window:

   ```sql
   BEGIN;
   ALTER TABLE public.audit_logs
       DISABLE TRIGGER trg_audit_logs_block_mutation;
   DELETE FROM public.audit_logs WHERE id IN ( ... LIMIT :batch_size );
   ALTER TABLE public.audit_logs
       ENABLE TRIGGER trg_audit_logs_block_mutation;
   COMMIT;
   ```

   This takes an `ACCESS EXCLUSIVE` lock and blocks inserts; use it only if the
   role-gated exception cannot land first. Never leave the trigger disabled.

3. **Alternative — partition `audit_logs` by `created_at`** and detach/drop
   whole months after the window. This avoids the trigger entirely (partition
   drop is DDL), at the cost of adding `created_at` to the audit PK and making
   audit_logs a future partitioning target.

This is a specification conflict: append-only is defined as "mutation blocked"
in DB-0.4, while DB-0.23 requires deletion after the retention window. The
exception must be explicit and auditable, not a silent bypass.

---

## 4. Soft-delete hard-delete window

Soft-deleted rows are user-visible rows with `deleted_at IS NOT NULL`. Hard
delete becomes eligible after `MUSAWIQ_RETENTION_SOFT_DELETE_DAYS` (default 30
days). The hard delete is not a generic cascade; each table has to pass its
reference guard.

Tables carrying `deleted_at` today or in the specification: `stores`, `users`,
`stored_files`, `products`, `product_concepts`, `landing_pages`, `posts`,
`creatives`. Any future `deleted_at` table joins this process.

Generic shape:

```sql
BEGIN;
SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '2s';

DELETE FROM public.<table> t
WHERE t.id IN (
    SELECT t2.id
    FROM public.<table> t2
    WHERE t2.deleted_at IS NOT NULL
      AND t2.deleted_at < now() - make_interval(days => :soft_days)
      AND NOT EXISTS ( /* table-specific reference guards */ )
    LIMIT :batch_size
);

COMMIT;
```

Table-specific rules:

- **`stores`** — a store owns the tenant graph. Do not hard delete until a
  tenant-erasure job has purged/archived every child table. For MVP, closed
  stores keep their row; `status = 'closed'` plus `deleted_at` is the retention
  marker. Audit rows referencing the store stay intact.
- **`users`** — referenced by `stores.owner_user_id`,
  `audit_logs.actor_user_id`, and many `created_by` / `requested_by` columns.
  Prefer **anonymisation** after the window (replace `email` with
  `deleted+<uuid>@invalid.local`, clear `full_name`, `phone`, `password_hash`,
  OAuth subject) and keep `id` for audit integrity. Hard delete only when no
  reference exists.
- **`products`** — `order_items.product_id` is a restricting FK; historical
  order lines keep the snapshot columns but the FK still blocks deletion. Keep
  the soft-deleted product row while any order item references it.
- **`product_concepts`** — FR-2.1.2 forbids hard delete when an `evaluation`
  exists. Restrict the purge accordingly; archive instead.
- **`landing_pages` / `posts` / `creatives`** — referenced by tests, campaigns,
  pages, and creatives. Hard delete only unreferenced rows; otherwise retain the
  soft-deleted row.
- **`stored_files`** — `status = 'deleted'` plus `deleted_at` is the soft
  delete. Delete the object from storage, then hard delete the row after the
  window when no other table references it. A staged file with no batch follows
  section 2.2 instead (no soft-delete wait required).

Hard delete must not remove audit history. Audit rows keep `target_type` and
`target_id`; they never contain the deleted PII payload.

---

## 5. Execution rules

Every purge phase (per table, per run) follows these rules.

1. **Role:** connect as `musawiq_maintenance` (DB-0.19). Guard at the start:

   ```sql
   DO $$
   BEGIN
       IF current_user <> 'musawiq_maintenance' THEN
           RAISE EXCEPTION 'retention must run as musawiq_maintenance, not %',
               current_user;
       END IF;
   END $$;
   ```

2. **Single-runner lock:** in the runner, before any phase:

   ```sql
   SELECT pg_try_advisory_lock(hashtext('musawiq_retention'));
   ```

   If it returns false, exit successfully; another run is active.

3. **Batches:** default `:batch_size = 5000` (audit and staging) or one
   partition per transaction. Each batch is its own transaction, with
   `statement_timeout` and `lock_timeout` set locally. Sleep 200–500 ms between
   batches so normal traffic is not starved.

4. **Idempotent:** each run computes its cutoff once, deletes with a bounded
   `LIMIT`, and never stores cursor state. Re-running after a crash is safe;
   already-deleted rows no longer match. Partition drops first check
   `to_regclass(...) IS NOT NULL` and that the partition's range is fully before
   the cutoff.

5. **Dry run by default:** the runner prints planned counts and takes no action
   unless `--execute` is passed. Counts come from the same predicates as the
   deletes.

6. **One audit row per phase:** write with the maintenance connection after the
   phase commits. `actor_type` is `service`, `store_id` and `actor_user_id` are
   `NULL`, and `metadata` carries `schema_version` (JSONB convention):

   ```sql
   INSERT INTO public.audit_logs (
       store_id, actor_user_id, actor_type, action,
       target_type, target_id, before, after, metadata,
       ip_hash, user_agent, correlation_id
   ) VALUES (
       NULL, NULL, 'service', 'retention.purge',
       'retention_run', :correlation_id, NULL, NULL,
       jsonb_build_object(
           'schema_version', 1,
           'job', 'retention',
           'table', :table_name,
           'cutoff', :cutoff,
           'deleted', :deleted,
           'batch_size', :batch_size
       ),
       NULL, 'retention-worker', :correlation_id
   );
   ```

   Use one `correlation_id` per run so all phase rows can be joined. A final
   `retention.run` row may summarise the totals.

7. **Never cascade:** no `DELETE ... CASCADE` in retention SQL. A blocked
   delete is a signal that the window or the reference guard is wrong.

8. **Verify after each phase:** `pg_constraint` has no invalid FKs, the target
   table has no rows before the cutoff outside legal holds, and the default
   partition was not used for event rows.

---

## 6. Schedule

| Cadence | Work |
| --- | --- |
| Daily, 02:00 UTC | Import staging (`import_issues` → `import_rows` → `import_batches`), staged files with no batch, soft-delete hard deletes |
| Daily, 02:30 UTC | `tracking_sessions` (only unreferenced), default-partition event rows if any |
| Weekly, Sunday 03:00 UTC | `audit_logs` batches (window >= 12 months), storage orphan reconciliation |
| Monthly, day 1 04:00 UTC | Drop old `events` and `metric_snapshots` partitions; run `fn_create_month_partition` for current + next two months |
| Quarterly | Review windows, dry-run report, row-count trend, legal-hold list |

The database-backed scheduler (async_jobs) or an external cron may drive these;
the job must still hold the advisory lock and run as `musawiq_maintenance`.

---

## 7. Observability and verification

- Emit per-phase counters: candidates, deleted, blocked-by-reference, duration.
- Alert when a phase deletes more than a configured percentage of a table, when
  the default partition is non-empty, when a partition is missing for the
  current month, or when a purge run is blocked by the same FK for two
  consecutive runs.
- Keep the last dry-run report as a build artefact.
- Verification query for audit floors:

  ```sql
  SELECT count(*) AS too_young
  FROM public.audit_logs
  WHERE created_at >= now() - interval '12 months'
    AND id IN (/* ids deleted by the last run */);
  ```

  The correct answer is zero.

---

## 8. Known conflicts with the current specification

1. **`audit_logs` append-only trigger vs. retention.** DB-0.4 blocks `DELETE`
   on `audit_logs`, but DB-0.23 requires deleting rows after the >= 12-month
   window. A role-gated trigger exception (section 3) or partitioning must be
   added in DB-0.19/DB-0.23; until then the purge job must use the temporary
   disable fallback.
2. **`orders.import_batch_id` vs. batch purge.** The FK is restricting, so a
   batch referenced by any imported order cannot be deleted, and the
   specification also requires import history to stay downloadable. Completed
   batches are therefore retained; purging them requires
   `ON DELETE SET NULL` or copying provenance into the order. This is a
   product decision, not something the purge job may silently work around.
3. **Soft delete vs. hard-delete FKs.** `product_concepts` with evaluations and
   products referenced by `order_items` cannot be hard deleted under current
   FKs; FR-2.1.2 explicitly forbids the first. Retention therefore annotates or
   anonymises these rows instead of deleting them.
4. **Session/event window ordering.** `events.tracking_session_id` and
   (from DB-0.13) `orders.tracking_session_id` restrict deletion of sessions.
   If the product configures a shorter session window than the event window,
   the purge cannot proceed; the windows must be ordered or the references must
   be relaxed.
5. **`stored_files` reference surface.** `import_batches.stored_file_id` and
   `error_report_file_id` are FKs, but several future tables reference stored
   files through nullable FKs and `uuid[]` arrays. The "no batch" rule is only
   safe for `purpose = 'sales_csv'` until every reference is enumerated.
