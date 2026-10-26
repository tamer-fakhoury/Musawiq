# AGENTS.md

Authoritative working agreement for every engineer on this repo.
Owner-maintained: do not edit. If a rule is wrong, report it.

## What this project is

Musawiq — a product-testing platform. Current phase: **Phase 0, database construction**.
No application code exists yet; `src/` is created in Phase 1.

## Source of truth, in order

1. `docs/Specifications.md` — entities, fields, conventions, ERD, OOP contracts
2. `docs/CONVENTIONS.md` — naming, layout, migration rules
3. `docs/backlog.md` — tasks and acceptance criteria
4. `docs/STATUS.md` — current state, gates, active assignments

If code and spec disagree, **stop and report**. Never silently reinterpret the spec.

## Environment

- PostgreSQL 18 (native `uuidv7()`, `NULLS NOT DISTINCT`)
- Python 3.11, venv at `.venv`
- `.env` (gitignored) provides `MUSAWIQ_ADMIN_DATABASE_URL` (superuser) and
  `MUSAWIQ_DATABASE_URL` (`musawiq_app`). Never print or commit secrets.

Always use the venv interpreter:

```
.venv\Scripts\python.exe -m <module>
```

## Commands

| Purpose | Command |
|---|---|
| Full verification | `.venv\Scripts\python.exe -m scripts.verify_all` |
| Migrations from empty | `.venv\Scripts\python.exe -m scripts.verify_db` |
| DB tests | `.venv\Scripts\python.exe -m pytest tests/db -q` |
| Tool tests | `.venv\Scripts\python.exe -m pytest tests/tools -q` |
| Audit tests | `.venv\Scripts\python.exe -m pytest tests/audit -q` |
| Schema docs drift | `.venv\Scripts\python.exe -m scripts.gen_schema_docs --check` |
| FK matrix drift | `.venv\Scripts\python.exe -m scripts.fk_matrix --check` |
| Schema audit | `.venv\Scripts\python.exe -m scripts.audit_schema --scratch` |

## Non-negotiable rules

- **One task per commit.** Commit message starts with the task ID: `db(0.14): ...`, `tools(0.13): ...`, `docs(0.20): ...`.
- **Stage explicitly:** `git add <paths>`. Never `git add -A` or `git add .`.
- **Never** amend, rebase, or revert another engineer's commit. Commit on top of current HEAD.
- **Never edit owner files:** `docs/STATUS.md`, `docs/backlog.md`, `docs/Specifications.md`,
  `docs/Requirements.md`, `docs/CONVENTIONS.md`, `AGENTS.md`, `scripts/verify_db.py`,
  `scripts/verify_all.py`, `scripts/parity_check.py`, `migrations/env.py`, `.env`.
- **Never edit an applied revision.** Fix forward in a new revision.
- **Physical tables are plural** (`stores`, `orders`, `users`); entity names in prose are singular.
- **Cross-domain FKs are deferred to DB-0.13.** Do not add FKs to tables that do not exist yet,
  and do not create placeholder tables.
- **Enums** are `text` + `CHECK`, never native `ENUM`.
- **Money** is `*_minor bigint` + `currency char(3)`; rates as inputs `*_bp int`; metrics `numeric(12,6)`.
- **Append-only** tables carry no `updated_at` and have a `fn_block_mutation` trigger.
- **JSONB** is for configuration/payloads/snapshots only and carries `schema_version`.
- `scripts/schema_manifest.py` is **yours**: update it in the same commit that creates or alters a table.

## Engineer scopes

| Engineer | Owns |
|---|---|
| 1 | `migrations/versions/`, `scripts/schema_manifest.py`, `tests/db/` |
| 2 | `src/` scaffold and application code (Phase 1); additive tooling when assigned |
| 3 | `docs/backlog-phase1.md` decomposition (when assigned) |

Do not touch another engineer's paths. If you need a change there, report it to the owner.

## Task loop

1. Read the task message and the relevant backlog section.
2. Implement only that task.
3. Run the required verification and capture the real output.
4. Commit once, with the task ID and evidence in the body.
5. Report: commit hash, files changed, exact command output, deviations.

## Testing standard (non-negotiable)

- **Tests cover acceptance criteria only.** One test per AC bullet is the target.
- **No stress, load, timing, or performance tests.** Performance tests are added only when a real regression appears, and only for that case.
- **No boundary/edge-case matrices, no property-based or fuzz tests, no combinatorial tables** unless the AC explicitly demands them.
- Happy path plus one failure path per AC is enough. Stop there.
- A task is accepted when every AC bullet is covered, not when coverage is maximal.


## Known debt (do not "fix" uninvited)

- 82 required FK columns unindexed → DB-0.14.
- 3 deferred FK candidates → DB-0.13.
- Seed lacks `decision_rule_sets` / `optimization_rule_sets` rows → DB-0.20b.
- `audit_schema.py`, `bench_db.py`, `gen_schema_docs.py`, `pii_scan.py`, `fk_matrix.py`,
  `seed_dev.py` each implement scratch-DB setup → consolidation pending.
