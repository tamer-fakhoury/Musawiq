# Partitioning Plan (DB-0.16)

Status: **plan only** — the MVP keeps `events`, `orders`, and `metric_snapshots`
as ordinary tables with `id uuid PRIMARY KEY`. Nothing in this document is
applied by a migration yet. It is the exact cutover plan to run when volume
justifies monthly range partitioning.

Target tables and partition keys:

| Table | Partition key | New primary key | Month boundary |
| --- | --- | --- | --- |
| `events` | `occurred_at timestamptz` | `(id, occurred_at)` | UTC |
| `orders` | `placed_at timestamptz` | `(id, placed_at)` | UTC |
| `metric_snapshots` | `period_start timestamptz` | `(id, period_start)` | UTC |

`events` and `metric_snapshots` do not exist at revision `0005`; their sections
describe the shape required when DB-0.10 creates them. `orders` exists now
(DB-0.5) and is the first candidate for conversion.

---

## 1. PostgreSQL constraints that drive the design

1. **The partition key must be part of every primary key and unique key on a
   partitioned table.** A partitioned table cannot keep `PRIMARY KEY (id)`.
   The MVP `id uuid` primary key therefore becomes `(id, <time column>)`.
2. **Every unique index must include the partition key.** This applies to
   partial unique indexes too. A unique index that omits the partition key
   cannot be created on the parent.
3. **A foreign key that references a partitioned table must target a unique key
   that includes the partition key.** Consequently, children referencing
   `orders` must carry `placed_at` (or another copy of the partition key) and
   use a composite FK `(order_id, order_placed_at) -> (id, placed_at)`.
   FKs *from* a partitioned table to ordinary tables are supported and need no
   change.
4. **Partition bounds are UTC.** Run all DDL with `SET TIME ZONE 'UTC'` so
   `date_trunc('month', ...)` produces stable bounds. Never create partitions
   using a session-local timezone.
5. **The partition key must be immutable in practice.** PostgreSQL can move a
   row when an `UPDATE` changes the partition key, but that rewrites the row,
   re-checks FKs, and defeats pruning. `occurred_at`, `placed_at`, and
   `period_start` are write-once by contract.
6. **The default partition must stay empty.** A row in the default partition
   inside a new month's range blocks `CREATE TABLE ... PARTITION OF`. Pre-create
   months ahead and alert if the default partition becomes non-empty.
7. **Local unique keys are only local.** A unique index on a partitioned table
   is enforced per partition. Global uniqueness needs an unpartitioned registry
   (see `events.event_id` and `orders` below).

---

## 2. Common cutover procedure

Run as the migration/owner role in a maintenance window. Stop writers first;
none of this is an online conversion.

```sql
SET statement_timeout = '0';
SET lock_timeout = '5s';
SET TIME ZONE 'UTC';
```

1. Capture the current definition:

   ```text
   pg_dump --schema-only --table=public.<table> <database> > <table>.before.sql
   ```

2. Free the `public` names and freeze the old rows. Moving the table to a
   legacy schema also moves its indexes, so the new parent can reuse the
   canonical index names:

   ```sql
   CREATE SCHEMA IF NOT EXISTS musawiq_legacy;

   BEGIN;
   LOCK TABLE public.<table> IN ACCESS EXCLUSIVE MODE;
   ALTER TABLE public.<table> SET SCHEMA musawiq_legacy;
   COMMIT;
   ```

3. Drop inbound FKs from child tables now. They currently point at the legacy
   table and must be recreated against the composite key. The per-table
   sections list the exact constraints.

4. Create the partitioned parent with the same columns, defaults, and CHECK
   constraints, but no PK/FK/indexes yet:

   ```sql
   CREATE TABLE public.<table> (
       LIKE musawiq_legacy.<table>
           INCLUDING DEFAULTS
           INCLUDING GENERATED
           INCLUDING STORAGE
           INCLUDING COMMENTS
           INCLUDING CONSTRAINTS
   ) PARTITION BY RANGE (<time_column>);
   ```

   `LIKE` always copies `NOT NULL`. It does **not** copy foreign keys, indexes,
   triggers, or the primary key, which is what we want.

5. Create one standalone table per month, copy that month, then attach it.
   Building each partition before attaching avoids a single long insert into
   the parent and lets the copy run in bounded transactions:

   ```sql
   DO $$
   DECLARE
       m date;
       first_month date;
       last_month date;
       part text;
   BEGIN
       SELECT date_trunc('month', min(<time_column>))::date,
              date_trunc('month', max(<time_column>))::date
         INTO first_month, last_month
         FROM musawiq_legacy.<table>;

       FOR m IN
           SELECT generate_series(first_month, last_month, interval '1 month')::date
       LOOP
           part := format('<table>_%s', to_char(m, 'YYYY_MM'));
           EXECUTE format(
               'CREATE TABLE public.%I (LIKE musawiq_legacy.<table> '
               'INCLUDING DEFAULTS INCLUDING GENERATED INCLUDING STORAGE '
               'INCLUDING COMMENTS INCLUDING CONSTRAINTS)',
               part
           );
           EXECUTE format(
               'INSERT INTO public.%I SELECT * FROM musawiq_legacy.<table> '
               'WHERE <time_column> >= %L AND <time_column> < %L',
               part,
               m::timestamp AT TIME ZONE 'UTC',
               (m + interval '1 month')::timestamp AT TIME ZONE 'UTC'
           );
           EXECUTE format(
               'ALTER TABLE public.<table> ATTACH PARTITION public.%I '
               'FOR VALUES FROM (%L) TO (%L)',
               part,
               m::timestamp AT TIME ZONE 'UTC',
               (m + interval '1 month')::timestamp AT TIME ZONE 'UTC'
           );
       END LOOP;
   END $$;
   ```

6. Add the composite primary key and every unique index on the parent (see the
   per-table sections). Build secondary indexes after the PK.
7. Create `public.<table>_default PARTITION OF public.<table> DEFAULT;`.
8. Recreate outbound FKs from the new parent and composite inbound FKs from
   children.
9. Recreate triggers on the parent. Row-level triggers on a partitioned parent
   are cloned to every partition, including future ones.
10. Validate: row counts and checksums match the legacy table, all constraints
    are `convalidated`, and `EXPLAIN` prunes partitions.
11. Drop the legacy table only after validation:

    ```sql
    DROP TABLE musawiq_legacy.<table>;
    ```

12. `ANALYZE public.<table>;` and run the application smoke tests.

The per-table sections below replace the `<placeholders>` and add the exact
keys for each target.

---

## 3. `events` — monthly on `occurred_at`

New primary key: `(id, occurred_at)`.

```sql
BEGIN;
LOCK TABLE public.events IN ACCESS EXCLUSIVE MODE;
CREATE SCHEMA IF NOT EXISTS musawiq_legacy;
ALTER TABLE public.events SET SCHEMA musawiq_legacy;
COMMIT;

-- No inbound FK references events (attribution.subject_id is polymorphic and
-- has no FK), so only outbound FKs are recreated later.

CREATE TABLE public.events (
    LIKE musawiq_legacy.events
        INCLUDING DEFAULTS INCLUDING GENERATED INCLUDING STORAGE
        INCLUDING COMMENTS INCLUDING CONSTRAINTS
) PARTITION BY RANGE (occurred_at);

ALTER TABLE public.events ALTER COLUMN occurred_at SET NOT NULL;

-- Backfill loop from section 2.5 with <table> = events,
-- <time_column> = occurred_at.

ALTER TABLE public.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (id, occurred_at);

-- event_id is no longer globally unique by itself (see section 5).
CREATE UNIQUE INDEX uq_events_event_id_occurred_at
    ON public.events (event_id, occurred_at);

CREATE INDEX ix_events_store_id_event_type_occurred_at
    ON public.events (store_id, event_type, occurred_at);
CREATE INDEX ix_events_tracking_session_id
    ON public.events (tracking_session_id);

CREATE TABLE public.events_default PARTITION OF public.events DEFAULT;

ALTER TABLE public.events
    ADD CONSTRAINT fk_events_store_id
        FOREIGN KEY (store_id) REFERENCES public.stores (id),
    ADD CONSTRAINT fk_events_tracking_session_id
        FOREIGN KEY (tracking_session_id) REFERENCES public.tracking_sessions (id),
    ADD CONSTRAINT fk_events_test_id
        FOREIGN KEY (test_id) REFERENCES public.tests (id),
    ADD CONSTRAINT fk_events_product_id
        FOREIGN KEY (product_id) REFERENCES public.products (id),
    ADD CONSTRAINT fk_events_campaign_id
        FOREIGN KEY (campaign_id) REFERENCES public.campaigns (id),
    ADD CONSTRAINT fk_events_adset_id
        FOREIGN KEY (adset_id) REFERENCES public.ad_sets (id),
    ADD CONSTRAINT fk_events_ad_variation_id
        FOREIGN KEY (ad_variation_id) REFERENCES public.ad_variations (id),
    ADD CONSTRAINT fk_events_event_type
        FOREIGN KEY (event_type) REFERENCES public.event_types (code);

CREATE TRIGGER trg_events_block_mutation
    BEFORE UPDATE OR DELETE ON public.events
    FOR EACH ROW EXECUTE FUNCTION fn_block_mutation();

-- Validate, then:
DROP TABLE musawiq_legacy.events;
```

FK impact: none inbound. The outbound FKs above are unchanged in shape; a
partitioned table may reference ordinary tables. Do not add an inbound FK from
`attributions`; `subject_id` is polymorphic by specification.

Retention handoff: DB-0.23 drops whole old `events_YYYY_MM` partitions instead
of deleting rows. `DROP TABLE` is DDL, so it does not fire the append-only
trigger.

---

## 4. `orders` — monthly on `placed_at`

New primary key: `(id, placed_at)`.

```sql
BEGIN;
LOCK TABLE public.orders IN ACCESS EXCLUSIVE MODE;
CREATE SCHEMA IF NOT EXISTS musawiq_legacy;
ALTER TABLE public.orders SET SCHEMA musawiq_legacy;
COMMIT;

-- Composite inbound FKs are added after the parent exists (section 5).

CREATE TABLE public.orders (
    LIKE musawiq_legacy.orders
        INCLUDING DEFAULTS INCLUDING GENERATED INCLUDING STORAGE
        INCLUDING COMMENTS INCLUDING CONSTRAINTS
) PARTITION BY RANGE (placed_at);

ALTER TABLE public.orders ALTER COLUMN placed_at SET NOT NULL;

-- Backfill loop from section 2.5 with <table> = orders,
-- <time_column> = placed_at.

ALTER TABLE public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id, placed_at);

-- Both existing uniques must now include the partition key.
CREATE UNIQUE INDEX uq_orders_store_id_external_order_id
    ON public.orders (store_id, external_order_id, placed_at)
    WHERE external_order_id IS NOT NULL;
CREATE UNIQUE INDEX uq_orders_store_id_dedupe_hash
    ON public.orders (store_id, dedupe_hash, placed_at)
    WHERE dedupe_hash IS NOT NULL;

CREATE INDEX ix_orders_store_id_test_id_test_phase
    ON public.orders (store_id, test_id, test_phase);
CREATE INDEX ix_orders_store_id_placed_at
    ON public.orders (store_id, placed_at);

CREATE TABLE public.orders_default PARTITION OF public.orders DEFAULT;

ALTER TABLE public.orders
    ADD CONSTRAINT fk_orders_store_id
        FOREIGN KEY (store_id) REFERENCES public.stores (id),
    ADD CONSTRAINT fk_orders_currency
        FOREIGN KEY (currency) REFERENCES public.currencies (code),
    ADD CONSTRAINT fk_orders_import_batch_id
        FOREIGN KEY (import_batch_id) REFERENCES public.import_batches (id);

-- Recreate the inbound FKs with composite keys (details in section 5), then:
DROP TABLE musawiq_legacy.orders;
```

FK impact:

| Child | Current reference | Required change |
| --- | --- | --- |
| `order_items.order_id` | `orders(id)` | Add `order_placed_at timestamptz`; copy from `orders.placed_at`; FK `(order_id, order_placed_at) -> orders(id, placed_at)`. |
| `import_rows.created_order_id` | `orders(id)` | Add nullable `created_order_placed_at`; use `MATCH FULL` so both columns are null or both are set. |
| `deposits.order_id` (DB-0.10) | `orders(id)` | New table: carry `order_placed_at` and use the composite FK from day one. |
| `attributions.subject_id` | polymorphic | No FK; unchanged. |

Example retrofit for `order_items`:

```sql
ALTER TABLE public.order_items DROP CONSTRAINT fk_order_items_order_id;
ALTER TABLE public.order_items ADD COLUMN order_placed_at timestamptz;

UPDATE public.order_items oi
   SET order_placed_at = o.placed_at
  FROM public.orders o
 WHERE o.id = oi.order_id;

ALTER TABLE public.order_items ALTER COLUMN order_placed_at SET NOT NULL;
ALTER TABLE public.order_items
    ADD CONSTRAINT fk_order_items_order_id
    FOREIGN KEY (order_id, order_placed_at)
    REFERENCES public.orders (id, placed_at)
    ON DELETE RESTRICT;
```

Example retrofit for the nullable `import_rows` reference:

```sql
ALTER TABLE public.import_rows
    DROP CONSTRAINT fk_import_rows_created_order_id;
ALTER TABLE public.import_rows
    ADD COLUMN created_order_placed_at timestamptz;

UPDATE public.import_rows r
   SET created_order_placed_at = o.placed_at
  FROM public.orders o
 WHERE o.id = r.created_order_id;

ALTER TABLE public.import_rows
    ADD CONSTRAINT fk_import_rows_created_order_id
    FOREIGN KEY (created_order_id, created_order_placed_at)
    REFERENCES public.orders (id, placed_at)
    MATCH FULL;
```

`MATCH FULL` makes the pair all-null or all-set; a stray half-reference is
rejected.

Prefer carrying the denormalized `order_placed_at` on `order_items` and
`deposits` from their first migration (DB-0.9/DB-0.10) rather than retrofitting
large child tables.

---

## 5. `metric_snapshots` — monthly on `period_start`

New primary key: `(id, period_start)`.

```sql
BEGIN;
LOCK TABLE public.metric_snapshots IN ACCESS EXCLUSIVE MODE;
CREATE SCHEMA IF NOT EXISTS musawiq_legacy;
ALTER TABLE public.metric_snapshots SET SCHEMA musawiq_legacy;
COMMIT;

CREATE TABLE public.metric_snapshots (
    LIKE musawiq_legacy.metric_snapshots
        INCLUDING DEFAULTS INCLUDING GENERATED INCLUDING STORAGE
        INCLUDING COMMENTS INCLUDING CONSTRAINTS
) PARTITION BY RANGE (period_start);

ALTER TABLE public.metric_snapshots ALTER COLUMN period_start SET NOT NULL;

-- Backfill loop from section 2.5 with <table> = metric_snapshots,
-- <time_column> = period_start.

ALTER TABLE public.metric_snapshots
    ADD CONSTRAINT metric_snapshots_pkey PRIMARY KEY (id, period_start);

-- The existing identity already contains period_start, so the only change is
-- to keep NULLS NOT DISTINCT.
CREATE UNIQUE INDEX uq_metric_snapshots_scope_period
    ON public.metric_snapshots
       (campaign_id, adset_id, ad_variation_id, period_start, period_end)
    NULLS NOT DISTINCT;

CREATE INDEX ix_metric_snapshots_campaign_id_period_start
    ON public.metric_snapshots (campaign_id, period_start);

CREATE TABLE public.metric_snapshots_default
    PARTITION OF public.metric_snapshots DEFAULT;

ALTER TABLE public.metric_snapshots
    ADD CONSTRAINT fk_metric_snapshots_store_id
        FOREIGN KEY (store_id) REFERENCES public.stores (id),
    ADD CONSTRAINT fk_metric_snapshots_test_id
        FOREIGN KEY (test_id) REFERENCES public.tests (id),
    ADD CONSTRAINT fk_metric_snapshots_campaign_id
        FOREIGN KEY (campaign_id) REFERENCES public.campaigns (id),
    ADD CONSTRAINT fk_metric_snapshots_adset_id
        FOREIGN KEY (adset_id) REFERENCES public.ad_sets (id),
    ADD CONSTRAINT fk_metric_snapshots_ad_variation_id
        FOREIGN KEY (ad_variation_id) REFERENCES public.ad_variations (id);

DROP TABLE musawiq_legacy.metric_snapshots;
```

FK impact: none inbound. `test_result_snapshots.source_metric_snapshot_ids` is
a `uuid[]` with no FK by specification. Outbound FKs above are unaffected.

---

## 6. Uniqueness and idempotency impact

### `events.event_id`

`UNIQUE (event_id)` is the ingestion idempotency key. On a partitioned table it
must become `(event_id, occurred_at)`, which is only unique **within a
partition**; the same client `event_id` can be inserted again in a later month.

Recommended: keep a small **unpartitioned** table as the global idempotency
registry:

```sql
CREATE TABLE public.event_ids (
    event_id uuid PRIMARY KEY,
    first_seen_at timestamptz NOT NULL DEFAULT now()
);
```

Ingestion does `INSERT INTO event_ids ... ON CONFLICT DO NOTHING` first and
only inserts the event when that row was new. The partitioned `events` table
keeps `(event_id, occurred_at)` for local lookup. If the product accepts
month-scoped idempotency instead, skip the registry and document that choice.

### `orders` dedupe keys

`UNIQUE (store_id, external_order_id)` and `UNIQUE (store_id, dedupe_hash)` must
gain `placed_at`. That weakens dedupe across a month boundary: an importer could
create a duplicate if the same `external_order_id` or `dedupe_hash` arrives with
a different `placed_at` in another month.

Options, in preference order:

1. Make the importer query the existing order across partitions before insert
   (index on `(store_id, external_order_id)` remains useful even though it is
   not unique) and keep `(store_id, external_order_id, placed_at)` as the local
   constraint.
2. Add an unpartitioned `order_dedupe` registry keyed by
   `(store_id, external_order_id)` and `(store_id, dedupe_hash)`.
3. Accept month-scoped uniqueness and document it.

Do not silently drop the global guarantee: FR-1.1.3/FR-1.1.5 depend on it.

### `metric_snapshots`

The existing unique key already includes `period_start`, so it survives the
conversion unchanged as long as `NULLS NOT DISTINCT` is preserved. Recreate it
with the partition key in the column list.

---

## 7. Default partition and monthly creation routine

Create the default partition once, after the backfill, and keep it empty:

```sql
CREATE TABLE public.events_default
    PARTITION OF public.events DEFAULT;
CREATE TABLE public.orders_default
    PARTITION OF public.orders DEFAULT;
CREATE TABLE public.metric_snapshots_default
    PARTITION OF public.metric_snapshots DEFAULT;
```

Creation routine (idempotent, UTC, refuses to create a range that already has
rows in the default partition):

```sql
CREATE OR REPLACE FUNCTION fn_create_month_partition(
    target_table regclass,
    partition_column text,
    month_start date
) RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    parent_schema text;
    parent_name text;
    partition_name text;
    default_relation regclass;
    range_start timestamptz;
    range_end timestamptz;
    existing regclass;
    has_rows boolean;
BEGIN
    SELECT n.nspname, c.relname
      INTO parent_schema, parent_name
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.oid = target_table;

    range_start := date_trunc('month', month_start)::timestamp AT TIME ZONE 'UTC';
    range_end := range_start + interval '1 month';
    partition_name := format('%s_%s', parent_name, to_char(range_start, 'YYYY_MM'));

    PERFORM pg_advisory_xact_lock(hashtext(target_table::text));

    existing := to_regclass(format('%I.%I', parent_schema, partition_name));
    IF existing IS NOT NULL THEN
        RETURN existing::text;
    END IF;

    default_relation := to_regclass(
        format('%I.%I', parent_schema, parent_name || '_default')
    );
    IF default_relation IS NOT NULL THEN
        EXECUTE format(
            'SELECT EXISTS (SELECT 1 FROM %s '
            'WHERE %I >= %L AND %I < %L)',
            default_relation, partition_column, range_start,
            partition_column, range_end
        ) INTO has_rows;
        IF has_rows THEN
            RAISE EXCEPTION
                'default partition % contains rows in [%, %); move them first',
                default_relation, range_start, range_end;
        END IF;
    END IF;

    EXECUTE format(
        'CREATE TABLE %I.%I PARTITION OF %I.%I '
        'FOR VALUES FROM (%L) TO (%L)',
        parent_schema, partition_name, parent_schema, parent_name,
        range_start, range_end
    );

    RETURN format('%I.%I', parent_schema, partition_name);
END;
$$;
```

Run it from the daily maintenance job (or `pg_cron`) so at least the current and
next two months always exist:

```sql
SELECT fn_create_month_partition(
    'public.events', 'occurred_at',
    (date_trunc('month', now()) + interval '2 months')::date
);
SELECT fn_create_month_partition(
    'public.orders', 'placed_at',
    (date_trunc('month', now()) + interval '2 months')::date
);
SELECT fn_create_month_partition(
    'public.metric_snapshots', 'period_start',
    (date_trunc('month', now()) + interval '2 months')::date
);
```

Partitioned indexes on the parent are automatically created on each new
partition; do not create per-partition indexes by hand.

---

## 8. Operational notes

- **Pruning:** every dashboard/report query must filter the partition key
  (`occurred_at`, `placed_at`, `period_start`) or PostgreSQL scans all
  partitions. Verify with `EXPLAIN (ANALYZE, BUFFERS)` that only the intended
  months appear.
- **Retention:** `events` is purged by detaching and dropping old monthly
  partitions (see `docs/RETENTION.md`). `DETACH PARTITION` takes a lock; prefer
  a maintenance window or `DETACH PARTITION ... CONCURRENTLY` where the
  PostgreSQL version and constraints allow it.
- **Monitoring:** alert when `<table>_default` is non-empty, when the next
  month's partition is missing, and when partition count or total size crosses
  the review threshold.
- **Rollback:** before dropping the legacy table, the conversion is reversible
  by dropping the new parent and moving the legacy table back with
  `ALTER TABLE ... SET SCHEMA public`. After the drop, restore from backup.

## 9. Verification checklist

- [ ] Row counts and per-month checksums match the legacy table.
- [ ] `events_pkey` / `orders_pkey` / `metric_snapshots_pkey` include the
      partition key.
- [ ] Every unique index on the parent includes the partition key.
- [ ] Inbound composite FKs exist, are `convalidated`, and have the intended
      `ON DELETE` behaviour.
- [ ] `pg_partition_tree()` shows the expected monthly children and the default.
- [ ] The default partition is empty.
- [ ] Monthly routine is idempotent (run twice; second call returns the same
      relation) and refuses overlapping default rows.
- [ ] The append-only trigger exists on `events` and its partitions.
- [ ] `EXPLAIN` prunes to one or a few partitions for time-filtered queries.
- [ ] Legacy schema dropped; `pg_dump --schema-only` diff reviewed.

## 10. Known conflicts with the current specification

1. **Global `event_id` uniqueness vs. partition-local uniqueness.** PostgreSQL
   cannot enforce a global unique index on a partitioned table unless the key
   contains the partition key. The registry table above (or month-scoped
   idempotency) is required; this must be accepted before partitioning events.
2. **Order dedupe keys vs. the partition key.** `(store_id,
   external_order_id)` and `(store_id, dedupe_hash)` must include `placed_at`,
   which weakens cross-month dedupe. The importer or a registry must preserve
   the FR-1.1.3/FR-1.1.5 guarantee.
3. **Inbound FKs require child columns.** `order_items`, `import_rows`, and the
   future `deposits` must carry `order_placed_at`; this is a schema change to
   child tables that the current spec does not mention.
4. **`SPECIFICATIONS.md` state:** the spec explicitly records that the MVP PK
   is `id uuid` and that partitioning "later requires the partition key in the
   PK" — this plan is the recorded follow-through, not a change to the MVP.
