# Project Status Ledger

Owner-maintained. The developer does not edit this file.
States: `not_started` → `in_review` → `changes_requested` → `accepted`.

## Phase 0 — Database Construction

| Task | State | Commit | Reviewed | Notes |
|---|---|---|---|---|
| DB-0.0 Scaffold + spec amendments | accepted | ff90ffb | 2026-10-25 | Offline alembic + compile + pytest collection verified; live DB run pending credentials |
| DB-0.1 Migration tooling baseline | accepted | 683f35b | 2026-10-25 | Offline chain verified owner-side; live `verify_db` pending `.env` |
| DB-0.2 Extensions & primitives | not_started | — | — | Blocked by DB-0.1 |
| DB-0.3 Reference data + seed | not_started | — | — | — |
| DB-0.4 Identity & tenancy | not_started | — | — | Gate G1 |
| DB-0.5 Integrations & ingestion | not_started | — | — | — |
| DB-0.6 Audience & context | not_started | — | — | — |
| DB-0.7 Product evaluation | not_started | — | — | — |
| DB-0.8 Recommendations | not_started | — | — | — |
| DB-0.9 Assets, campaigns & tests | not_started | — | — | — |
| DB-0.10 Measurement | not_started | — | — | — |
| DB-0.11 Optimization | not_started | — | — | — |
| DB-0.12 Decision & investment | not_started | — | — | Gate G2 follows DB-0.13 |
| DB-0.13 Integrity gate | not_started | — | — | Gate G2 |
| DB-0.14 Indexing | not_started | — | — | — |
| DB-0.15 RLS & tenancy | not_started | — | — | Gate G3 |
| DB-0.16 Partitioning readiness | not_started | — | — | Docs only |
| DB-0.17 Concurrency | not_started | — | — | — |
| DB-0.18 PII & encryption | not_started | — | — | — |
| DB-0.19 Roles & privileges | not_started | — | — | — |
| DB-0.20 Seeds & fixtures | not_started | — | — | — |
| DB-0.21 Verification pipeline | not_started | — | — | Gate G4 |
| DB-0.22 Performance baseline | not_started | — | — | — |
| DB-0.23 Retention & purge | not_started | — | — | — |
| DB-0.24 Schema docs & traceability | not_started | — | — | Phase 0 exit |

## Phase 1+ — Application

Not started. No `FR-*` task may begin before Phase 0 exit.

## Review Log

| Date | Task | Verdict | Reason |
|---|---|---|---|
| 2026-10-25 | DB-0.0 | accepted | Scaffold, spec amendments A1–A11, ledger created |
| 2026-10-25 | DB-0.1 | accepted | Single file, empty baseline chain; developer's 5 findings upheld |

## Environment

- PostgreSQL: **18.3** (adopted; native `uuidv7()`, `NULLS NOT DISTINCT`)
- Python: 3.11.3
- Git: 2.40.1
- Verification: `python -m scripts.verify_db` (no CI host)
- Credentials: `.env` (gitignored), maintained by the project owner
- **BLOCKER:** `.env` does not exist yet. Live `verify_db` cannot run.
