# Conventions

Owner-owned document. The developer follows it; only the owner edits it.

## Repository layout

```
alembic.ini                  migration config (no credentials)
migrations/
  env.py                     Alembic environment (owner-owned)
  script.py.mako             revision template
  versions/NNNN_slug.py      one revision per DB task
scripts/
  verify_db.py               local verification pipeline (owner-owned)
  parity_check.py            manifest parity check (owner-owned)
  schema_manifest.py         declared tables/columns (developer-maintained)
tests/db/                    structural, constraint, RLS, parity tests
docs/                        Requirements, Specifications, backlog, STATUS
```

## Migrations

- One revision per DB task, revision IDs are ordinals: `0001`, `0002`, ...
- File names are `NNNN_<scope>.py`. The `file_template` in `alembic.ini` is only a default;
  an explicit filename that matches `NNNN_<scope>.py` is always acceptable.
- `down_revision` forms a single linear chain. No branches, no multiple heads.
- `upgrade()` and `downgrade()` must both be real. `down` must restore the prior state.
- Write explicit SQL with `op.execute()`. Do not use autogenerate output as the source of truth.
- Never edit an applied revision. Fix forward with a new revision.
- Every revision has a module docstring naming the DB task it implements.

## Naming

- Tables: `snake_case`, plural (`orders`, `order_items`).
- Columns: `snake_case`.
- Money: `<name>_minor` + `currency char(3)`.
- Rates as inputs: `<name>_bp` (basis points).
- Computed metrics: `numeric(12,6)`.
- Timestamps: `created_at`, `updated_at` (`timestamptz`).
- Booleans: `is_*`, `has_*`.
- Named constraints:
  - `ck_<table>_<rule>`
  - `fk_<table>_<column>`
  - `uq_<table>_<columns>`
  - `ix_<table>_<columns>`
- Triggers: `trg_<table>_<purpose>`; functions: `fn_<purpose>`.

## Schema rules

- Primary key: `id uuid PRIMARY KEY DEFAULT uuidv7()` (PostgreSQL 18 native).
- Enum-like columns: `text` + `CHECK`. Native `ENUM` types are forbidden.
- Nullable columns inside a `UNIQUE` constraint require `NULLS NOT DISTINCT`.
- Append-only tables: no `updated_at`, mutation blocked by trigger.
- Encrypted payloads: `bytea`. Never store ciphertext in `jsonb`.
- No raw IP addresses anywhere; store `ip_hash char(64)`.
- JSONB columns carry a `schema_version` key.
- Reference columns that cannot be FK-enforced (`uuid[]`, polymorphic `target_id`) are
  documented in `Specifications.md` under Integrity exceptions.

## Manifest

- `scripts/schema_manifest.py` must be updated in the same commit that creates or alters a table.
- It is the machine-checkable projection of `Specifications.md`; parity fails if it drifts.

## Verification

```
.venv\Scripts\python.exe -m scripts.verify_db
```
Expected when RLS is not yet implemented: `5 passed, 2 skipped`.

Add `--expect-rls` from DB-0.15 onward.
