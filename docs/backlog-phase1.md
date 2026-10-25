# Phase 1 Backlog - Atomic Task Decomposition

Status: planning artifact for the Project Owner. This file decomposes the Phase 1
application work into atomic, independently testable tasks.

Sources, in authority order:

1. `docs/Specifications.md` - entities, fields, conventions, OOP contracts
2. `docs/CONVENTIONS.md` - naming and layout
3. `docs/backlog.md` - Phase 0 history, Phase 1 FR detail, delivery slices
4. `docs/Requirements.md` - FR acceptance criteria
5. `docs/STATUS.md` - current phase gate

**Entry gate.** No Phase 1 task starts until Phase 0 is green through DB-0.24,
including DB-0.21 (verification pipeline), DB-0.15 (RLS), and DB-0.17
(concurrency). This document is only a plan; it does not open the gate.

**MVP cut.** Slices A + B + C + D + E, plus FR-4.2.5 (optimization
recommendations only). FR-4.2.1-FR-4.2.4 are decomposed for completeness but are
post-MVP. FR-4.2.6 is an explicit non-goal and is not decomposed.

## How to use this backlog

- Each task is sized for one engineer, one day or less, one commit, and an
  independent test.
- Task IDs are stable. Do not renumber completed tasks; append new ones.
- `DEPENDS ON` is a hard ordering constraint. `BLOCKED BY` is a decision or
  external dependency that must be resolved before implementation starts.
- `TOUCHES` names the expected files/areas under the scaffold layout below. The
  scaffold owner may adjust the exact directory names once, before Wave A1
  starts; task scope and contract do not change.
- Every task inherits the cross-cutting definition of done below. Acceptance
  criteria list only task-specific additions.
- If a task cannot be completed without inventing a rule, stop and raise it
  under `## Open decisions`; do not silently choose business logic.

### Cross-cutting definition of done

Every task must satisfy all of the following:

- `CC-1` through `CC-11` from `docs/Requirements.md` apply.
- Server-side authorization and store scoping are enforced; cross-store access
  returns 403/404 and emits a security event.
- Money uses `*_minor bigint` plus `currency char(3)`; timestamps are UTC in
  storage and rendered in the store timezone.
- User-facing errors use the shared error envelope: stable code, actionable
  message, correlation/job ID, no stack trace and no secrets.
- Structured logs include `store_id`, `actor_user_id`, `correlation_id`, and a
  job ID where the work is asynchronous.
- Tests include unit tests plus the relevant integration, tenant-isolation, and
  end-to-end coverage. A task that changes an API also updates its OpenAPI
  contract.
- No Phase 1 task edits an owner file (`docs/STATUS.md`, `docs/backlog.md`,
  `docs/Specifications.md`, `docs/Requirements.md`, `docs/CONVENTIONS.md`,
  `AGENTS.md`) or an applied migration.
- New JSONB payloads carry `schema_version`.
- AI-generated or AI-derived output is labeled as such and stores its model or
  template version plus an input snapshot reference.

### Proposed scaffold layout

The application scaffold is being created by Engineer 2. This backlog assumes
the following layout; confirm or adjust it in `P1-A1` before Wave A begins.

```text
src/musawiq/
  main.py                 application entrypoint and router wiring
  config.py               environment-backed settings
  db.py                   engine, session, transaction helpers
  api/                    HTTP routers and request/response schemas
  domain/                 entities, value objects, enums, policies
  services/               use cases and domain services
  repositories/           SQL persistence and query objects
  workers/                async job handlers and scheduler
  integrations/           external adapters (ecommerce, ads, AI, storage)
  middleware/             auth, tenancy, correlation, error handling
  web/                    server-rendered public landing pages
  templates/              landing-page and email templates
  static/                 first-party tracking script and page assets
tests/
  unit/                   pure domain and service tests
  integration/            database/API/job tests
  isolation/              cross-store and RLS tests
  e2e/                    critical user-flow tests
```

Admin-SPA framework, if any, is an open decision (`P1-DEC-10`). Tasks expose
versioned HTTP contracts and server-rendered public pages; they do not assume a
particular admin frontend.

## Traceability

Legend: `MVP` = in the recommended Phase 1 cut; `Post-MVP` = decomposed but
sequenced after the cut; `Blocked` = implementation waits on an open decision.

| FR | Requirement | Slice | Atomic task(s) | Release |
|---|---|---|---|---|
| FR-0.1 | Store data isolation | A | P1-A2, P1-A4 | MVP |
| FR-0.2 | Roles and spend approval | A | P1-A3 | MVP |
| FR-0.3 | Audit trail | A | P1-A4 | MVP |
| FR-0.4 | Async jobs, idempotency, and status | A | P1-A5 | MVP |
| FR-0.5 | AI/model governance and degraded mode | A | P1-A6, P1-C8 | MVP |
| FR-1.1.1 | CSV upload and format validation | A | P1-A7, P1-A8 | MVP |
| FR-1.1.2 | Column mapping | A | P1-A9 | MVP |
| FR-1.1.3 | Row validation and duplicate detection | A | P1-A10 | MVP |
| FR-1.1.4 | Preview and error review before commit | A | P1-A11 | MVP |
| FR-1.1.5 | Commit and import summary | A | P1-A12 | MVP |
| FR-1.1.6 | E-commerce integration connect and historical import | B | P1-B8, P1-B9 | Blocked: D1 |
| FR-1.2.1 | Product category and niche | A | P1-A13 | MVP |
| FR-1.2.2 | Target customer profile | A | P1-A14 | MVP |
| FR-1.2.3 | Customer feedback intake | A | P1-A16 | MVP |
| FR-1.2.4 | Save, version, and consume audience profile | A | P1-A15 | MVP |
| FR-2.1.1 | Create a product concept with validation | B | P1-B1 | MVP |
| FR-2.1.2 | Manage multiple concepts and lifecycle | B | P1-B2 | MVP |
| FR-2.1.3 | Data sufficiency assessment | B | P1-B3 | MVP |
| FR-2.1.4 | Viability scoring | B | P1-B4, P1-B5 | MVP |
| FR-2.1.5 | Score explanation and limitations | B | P1-B6 | MVP |
| FR-2.1.6 | Compare, sort, and select concepts | B | P1-B7 | MVP |
| FR-2.2.1 | Generate recommendations | C | P1-C1 | MVP |
| FR-2.2.2 | Rationale and evidence provenance | C | P1-C3 | MVP |
| FR-2.2.3 | Save or dismiss ideas | C | P1-C2 | MVP |
| FR-2.2.4 | Convert an idea into a product concept | C | P1-C4 | MVP |
| FR-3.1.1 | Product input and page options | C | P1-C7 | MVP |
| FR-3.1.2 | Generate a responsive landing page | C | P1-C6, P1-C9 | MVP |
| FR-3.1.3 | Product copy generation and editing | C | P1-C8 | MVP |
| FR-3.1.4 | Ordering mechanism | C | P1-C10 | MVP |
| FR-3.1.5 | Preview, edit, publish, and shareable URL | C | P1-C11 | MVP |
| FR-3.2.1 | Generate ad copy variations | C | P1-C12 | Blocked: D1 |
| FR-3.2.2 | Review, edit, approve, or discard variations | C | P1-C13 | MVP |
| FR-3.2.3 | Campaign configuration | C | P1-C14 | Blocked: D1 |
| FR-3.2.4 | Campaign association and tracking parameters | C | P1-C15 | MVP |
| FR-3.2.5 | Validation and preview before submission | C | P1-C16 | MVP |
| FR-3.2.6 | Advertising account authorization | C | P1-C17, P1-B8 | Blocked: D1 |
| FR-3.2.7 | Publish campaign and report status | C | P1-C18 | Blocked: D1 |
| FR-4.1.1 | Event model and ingestion | D | P1-D1 | MVP |
| FR-4.1.2 | Landing-page visit and interaction tracking | D | P1-D2, P1-D3 | MVP |
| FR-4.1.3 | WhatsApp click tracking | D | P1-D4 | MVP |
| FR-4.1.4 | COD order form and submission | D | P1-D5 | MVP |
| FR-4.1.5 | Deposit confirmation | D | P1-D6 | MVP |
| FR-4.1.6 | Attribution rules | D | P1-D7 | MVP |
| FR-4.1.7 | Conversion metrics dashboard | D | P1-D8 | MVP |
| FR-4.2.1 | Scheduled metrics sync | F | P1-F1 | Post-MVP |
| FR-4.2.2 | KPI calculation | F | P1-F2 | Post-MVP |
| FR-4.2.3 | Thresholds and minimum-data configuration | F | P1-F3 | Post-MVP |
| FR-4.2.4 | Underperformer and promising-ad detection | F | P1-F4 | Post-MVP |
| FR-4.2.5 | Optimization recommendations (MVP) | F | P1-F5 | MVP |
| FR-4.2.6 | Approved or opt-in automated execution | F | - | Deferred non-goal; see below |
| FR-4.2.7 | Budget guardrails, audit, and kill switch | F | P1-F6 | MVP guardrails only |
| FR-5.1.1 | Retrieve test results | E | P1-E1 | MVP |
| FR-5.1.2 | Verdict KPI calculation | E | P1-E2 | MVP |
| FR-5.1.3 | Decision rule configuration | E | P1-E3 | MVP |
| FR-5.1.4 | Verdict classification | E | P1-E4 | MVP |
| FR-5.1.5 | Verdict explanation and limitations | E | P1-E6 | MVP |
| FR-5.1.6 | Inconclusive test detection | E | P1-E5 | MVP |
| FR-5.1.7 | Extend a test | E | P1-E7 | MVP |
| FR-5.2.1 | Collect investment inputs | E | P1-E8 | MVP |
| FR-5.2.2 | Demand estimation with stated assumptions | E | P1-E9 | MVP |
| FR-5.2.3 | Unit economics | E | P1-E10 | MVP |
| FR-5.2.4 | Compute feasible order quantities | E | P1-E11 | MVP |
| FR-5.2.5 | Scenario presentation and risk | E | P1-E12 | MVP |
| FR-5.2.6 | Adjust assumptions and recalculate with versioning | E | P1-E13 | MVP |

**Unmapped FR.** FR-4.2.6 has no atomic task because automated budget
reallocation is an explicit non-goal for this Phase 1. The entity
`optimization_actions` and the `optimization_rule_sets` schema remain reserved
for Phase 2; do not add execution paths in Phase 1.

**FR count note.** `docs/Requirements.md` contains 64 FR headings. The stated
"58 FR items" is the MVP cut: it excludes FR-4.2.1-FR-4.2.4 and
FR-4.2.6-FR-4.2.7 from Module 4.2. All 64 headings are listed above; 63 are
mapped and FR-4.2.6 is intentionally unmapped.

## Slice A - Foundation and onboarding

### P1-A1 Application scaffold and operational baseline

**TASK:** Complete the application scaffold with configuration, database session
management, structured logging, error envelope, health endpoint, and the test
harness the rest of Phase 1 uses.

**ACCEPTANCE CRITERIA:**
- `GET /health` returns liveness and database-connectivity status without exposing
  credentials or internal paths.
- Configuration is environment-backed, validated at startup, and fails fast on a
  missing required value; no secret is logged.
- The database session helper supports read-only and transactional use and is
  reused by repositories.
- The shared error envelope and correlation-ID middleware are wired into the
  application.
- Unit and integration test fixtures exist; `pytest` passes on a clean checkout
  with the same database URL rules as Phase 0.

**DEPENDS ON:** none (Engineer 2 scaffold is the starting point)

**TOUCHES:** `src/musawiq/main.py`, `src/musawiq/config.py`,
`src/musawiq/db.py`, `src/musawiq/api/health.py`,
`src/musawiq/middleware/errors.py`, `tests/`

**FR:** FR-0.1 (platform baseline), all cross-cutting criteria

### P1-A2 Tenant context and store scoping

**TASK:** Implement authenticated tenant context, repository-level store scoping,
and the cross-store denial path for every tenant-owned query.

**ACCEPTANCE CRITERIA:**
- Request middleware resolves `store_id`, `user_id`, and `role` from the
  authenticated session; unauthenticated requests are rejected.
- Every repository read/write for a tenant table applies the store filter; a
  bypass is impossible without an explicit maintenance role.
- Cross-store access returns 403 or 404 consistently and emits a security event
  with actor, target, and correlation ID.
- Isolation tests cover products, orders, imports, concepts, campaigns, events,
  and metrics.
- Store deletion follows the documented retention/deletion process and cannot
  orphan tenant rows.

**DEPENDS ON:** P1-A1

**TOUCHES:** `src/musawiq/middleware/tenant.py`,
`src/musawiq/repositories/base.py`, `src/musawiq/api/deps.py`,
`tests/isolation/`

**FR:** FR-0.1

### P1-A3 Role permission matrix and authorization service

**TASK:** Implement the Owner/Manager/Analyst permission matrix and a
server-side authorization check used by every privileged use case.

**ACCEPTANCE CRITERIA:**
- A documented matrix lists read, write, publish-page, submit-campaign,
  approve-budget, extend-test, and accept-recommendation actions per role.
- Only Owner and Manager can publish pages, submit campaigns, or approve budget
  changes; Analyst is read-only for those actions.
- Unauthorized attempts return a clear 403 without leaking resource existence.
- Every privileged action records the acting user.
- Unit tests cover every role-action cell in the matrix.

**DEPENDS ON:** P1-A2

**TOUCHES:** `src/musawiq/domain/permissions.py`,
`src/musawiq/services/authorization.py`, `src/musawiq/api/deps.py`,
`tests/unit/test_permissions.py`, `docs/PERMISSIONS.md`

**FR:** FR-0.2

### P1-A4 Audit service and immutable query surface

**TASK:** Implement append-only audit writes and a filtered, exportable audit
read API.

**ACCEPTANCE CRITERIA:**
- `IAuditService.log` writes actor, store, action, target, UTC timestamp, and
  before/after JSONB for the actions named by the FR.
- No update or delete route exists for audit rows; attempts fail at the service
  boundary and are blocked by the database trigger.
- Owner can filter by date range, user, and target type/ID, and export the
  result.
- Audit writes are part of the caller's transaction where the action is
  transactional, and use a separate correlation ID where the action is async.
- PII is excluded or hashed before writing; tests assert no raw IP, token, or
  address is stored.

**DEPENDS ON:** P1-A1, P1-A2, P1-A3

**TOUCHES:** `src/musawiq/services/audit.py`,
`src/musawiq/repositories/audit_logs.py`, `src/musawiq/api/audit.py`,
`tests/integration/test_audit.py`

**FR:** FR-0.3, FR-0.1

### P1-A5 Async job queue, worker lifecycle, and idempotency

**TASK:** Implement the database-backed async job lifecycle, idempotency keys,
correlation IDs, retry/backoff, and progress reporting.

**ACCEPTANCE CRITERIA:**
- Jobs support queued, running, succeeded, failed, partial, and cancelled states
  with attempt count and max attempts.
- `enqueue` with an existing idempotency key returns the existing job instead of
  creating a duplicate.
- A worker claims jobs safely, records progress, and exposes start/finish
  timestamps.
- Failures store a human-readable error code and message plus the correlation
  ID; a safe manual retry path exists.
- Tests cover duplicate enqueue, worker crash recovery, retry, and cancellation.

**DEPENDS ON:** P1-A1, P1-A3

**TOUCHES:** `src/musawiq/domain/jobs.py`, `src/musawiq/services/jobs.py`,
`src/musawiq/workers/runner.py`, `src/musawiq/repositories/async_jobs.py`,
`src/musawiq/middleware/correlation.py`, `tests/integration/test_jobs.py`

**FR:** FR-0.4

### P1-A6 AI governance, versioning, and degraded mode

**TASK:** Implement the shared AI-output contract: model/template version, input
snapshot, AI labeling, and graceful dependency-failure handling.

**ACCEPTANCE CRITERIA:**
- A common wrapper records model/provider version, prompt or template version,
  input snapshot reference, and timestamp for every AI output.
- The wrapper exposes a typed degraded-mode result when the provider times out,
  is rate-limited, or is unavailable; callers return a clear message and retry
  option.
- AI-generated content carries an `ai_generated` label in API payloads and
  rendered pages.
- No merchant data is sent to a shared training path; the opt-in flag is read
  from configuration and defaults to off.
- Contract tests use a fake provider and prove no fabrication path exists when
  the provider returns no evidence.

**DEPENDS ON:** P1-A1, P1-A4

**TOUCHES:** `src/musawiq/services/ai_governance.py`,
`src/musawiq/domain/ai.py`, `src/musawiq/integrations/ai/base.py`,
`tests/unit/test_ai_governance.py`

**FR:** FR-0.5

### P1-A7 File storage adapter and safe upload validation

**TASK:** Implement the file-storage abstraction, staged upload, checksum, size
and type validation, and the stored-file metadata API.

**ACCEPTANCE CRITERIA:**
- Uploads write to the configured storage backend and create a `stored_files`
  row with purpose, filename, MIME type, size, checksum, provider, key, and
  status `staged`.
- Extension, MIME, size ceiling, encoding, and empty-file checks produce specific
  errors before any domain record is written.
- Downloads use short-lived signed references or an equivalent protected route;
  storage keys and credentials never appear in responses.
- A deletion path marks `status = deleted` and follows the retention policy.
- Tests cover accepted files, each rejection class, and tenant isolation.

**DEPENDS ON:** P1-A1, P1-A2, P1-A4

**BLOCKED BY:** P1-DEC-3 (storage backend and key management)

**TOUCHES:** `src/musawiq/integrations/storage/`,
`src/musawiq/services/files.py`, `src/musawiq/api/files.py`,
`src/musawiq/repositories/stored_files.py`, `tests/integration/test_files.py`

**FR:** FR-1.1.1

### P1-A8 CSV upload, template, and staged batch creation

**TASK:** Implement CSV upload that stages a file and creates an import batch
without writing any sales records.

**ACCEPTANCE CRITERIA:**
- Accepts `.csv` up to the configured limit and exposes a downloadable template.
- Rejects unsupported extension, MIME type, encoding, or empty content with a
  specific error.
- A successful upload creates a `stored_files` row with purpose `sales_csv` and a
  new `import_batches` row in `uploaded` state.
- No product, order, or order-item row is created at upload time.
- API returns the batch ID, filename, size, and next action.

**DEPENDS ON:** P1-A7

**TOUCHES:** `src/musawiq/services/imports/upload.py`,
`src/musawiq/api/imports.py`, `src/musawiq/repositories/import_batches.py`,
`tests/integration/test_import_upload.py`

**FR:** FR-1.1.1

### P1-A9 Column mapping and suggestions

**TASK:** Implement column discovery, heuristic mapping suggestions, one-to-one
validation, and reusable column mappings per store.

**ACCEPTANCE CRITERIA:**
- Required targets are `product_id`, `product_name`, `order_date`, `quantity`,
  and `sales_amount`; optionals are `order_id`, `currency`, and `sku`.
- Suggestions are scored by normalized header-name similarity and shown with
  three sample values per source column.
- Merchant overrides win; one source column maps to one target field.
- Saving a mapping persists a `column_mappings` row scoped to the store and
  reusable by later batches.
- Import validation cannot start while a required target is unmapped.

**DEPENDS ON:** P1-A8

**TOUCHES:** `src/musawiq/services/imports/mapping.py`,
`src/musawiq/repositories/column_mappings.py`,
`src/musawiq/repositories/import_rows.py`, `src/musawiq/api/imports.py`,
`tests/integration/test_import_mapping.py`

**FR:** FR-1.1.2

### P1-A10 Import row validation and duplicate detection

**TASK:** Implement the validation job that parses mapped rows into staged
import rows and records field-level issues and duplicate status.

**ACCEPTANCE CRITERIA:**
- Validates required values, store-timezone date parsing, integer quantity > 0,
  amount >= 0, known ISO currency, and product consistency.
- Duplicate rule is `order_id + product_id` when an order ID exists; otherwise a
  stable hash of product, date, quantity, and amount.
- Detection covers duplicates within the file and against existing orders using
  the same dedupe hash contract as imports.
- Strict mode marks the batch failed on any invalid row; lenient mode marks
  invalid rows skipped and continues.
- Every issue stores row number, field, issue code, message, and raw value; the
  job reports progress and is retry-safe.

**DEPENDS ON:** P1-A9, P1-A5

**TOUCHES:** `src/musawiq/services/imports/validation.py`,
`src/musawiq/workers/import_validate.py`,
`src/musawiq/repositories/import_rows.py`,
`src/musawiq/repositories/import_issues.py`,
`tests/integration/test_import_validation.py`

**FR:** FR-1.1.3

### P1-A11 Import preview, counts, error report, and cancel

**TASK:** Implement the read-only preview and error-report surface and a cancel
path that removes only staged rows.

**ACCEPTANCE CRITERIA:**
- Preview returns paginated valid-row samples plus all issues or a downloadable
  error report file.
- Counts returned are total, valid, invalid, duplicates, imported, and skipped.
- No domain row is written by preview or error-report generation.
- Cancel sets the batch to `cancelled` and deletes only its `import_rows` and
  `import_issues`.
- Preview is store-scoped and returns 404 for another store's batch.

**DEPENDS ON:** P1-A10

**TOUCHES:** `src/musawiq/services/imports/preview.py`,
`src/musawiq/api/imports.py`, `src/musawiq/repositories/import_rows.py`,
`src/musawiq/repositories/import_issues.py`,
`tests/integration/test_import_preview.py`

**FR:** FR-1.1.4

### P1-A12 Import commit, summary, history, and idempotent re-upload

**TASK:** Implement the transactional commit from staged rows to products,
orders, and order items, with summary, history, and duplicate-safe retry.

**ACCEPTANCE CRITERIA:**
- Commit writes accepted rows in one transaction with `import_batch_id` on each
  order; a failure leaves domain tables unchanged and marks the batch failed.
- Rows sharing `external_order_id` group into one order with multiple order
  items; rows without an order ID create one order each.
- Product upsert is scoped by store and matches on external product ID or SKU;
  the update policy is an explicit merchant choice and never silently overwrites.
- Summary returns imported, skipped, rejected, duplicates, duration, and date
  range; import history is listable and the error report remains downloadable.
- Re-uploading the same file checksum plus store returns the original summary
  instead of inserting duplicates.
- Strict-mode failure and lenient-mode partial success both have tests.

**DEPENDS ON:** P1-A10, P1-A11, P1-A5, P1-A4

**TOUCHES:** `src/musawiq/services/imports/commit.py`,
`src/musawiq/workers/import_commit.py`, `src/musawiq/repositories/products.py`,
`src/musawiq/repositories/orders.py`,
`src/musawiq/repositories/order_items.py`, `src/musawiq/api/imports.py`,
`tests/integration/test_import_commit.py`

**FR:** FR-1.1.5

### P1-A13 Category and niche selection

**TASK:** Implement category-tree browsing, store niche selection, and custom
niche creation with validation.

**ACCEPTANCE CRITERIA:**
- Merchant can browse active categories and select one or more; an active niche
  must belong to a selected category or be global.
- Custom niche creation is store-scoped, length-limited, and uses the partial
  unique `(store_id, slug)` rule.
- At least one category is required when saving the store profile.
- The selection is persisted and returned with the store profile.
- Tests cover taxonomy validation, duplicate custom slug, and cross-store
  isolation.

**DEPENDS ON:** P1-A2, P1-A3

**TOUCHES:** `src/musawiq/services/taxonomy.py`,
`src/musawiq/api/taxonomy.py`,
`src/musawiq/repositories/categories.py`,
`src/musawiq/repositories/niches.py`, `tests/integration/test_taxonomy.py`

**FR:** FR-1.2.1

### P1-A14 Audience profile and segments

**TASK:** Implement create/edit of audience profiles and multiple segments with
location, age, gender, interest, and language validation.

**ACCEPTANCE CRITERIA:**
- A profile captures selected niche IDs, languages, notes, and a status; a store
  can have one current profile.
- Segments support multiple rows per profile with `age_min <= age_max`, bounds
  0-120, locations from the country reference data, and optional empty fields.
- Invalid age ranges and unknown locations return field-level errors.
- `upsertProfile` and `upsertSegment` are store-scoped and permission-checked.
- Unit tests cover validation; integration tests cover create, edit, and
  cross-store denial.

**DEPENDS ON:** P1-A2, P1-A3, P1-A13

**TOUCHES:** `src/musawiq/services/audience.py`,
`src/musawiq/api/audience.py`,
`src/musawiq/repositories/audience_profiles.py`,
`src/musawiq/repositories/audience_segments.py`,
`tests/integration/test_audience.py`

**FR:** FR-1.2.2

### P1-A15 Audience profile versioning and current-version semantics

**TASK:** Implement immutable profile versioning so each save creates a new
version and evaluations can reference the exact version used.

**ACCEPTANCE CRITERIA:**
- Each save increments `version`, inserts a new row with `is_current = true`,
  and demotes the prior current row in one transaction.
- Partial unique `(store_id)` where `is_current` is enforced and tested.
- Version history is listable with actor and timestamp.
- Editing a profile never modifies a prior version; consumers read the version
  ID they recorded.
- `getCurrentProfile` is deterministic under concurrent saves.

**DEPENDS ON:** P1-A14

**TOUCHES:** `src/musawiq/services/audience.py`,
`src/musawiq/repositories/audience_profiles.py`,
`src/musawiq/api/audience.py`, `tests/integration/test_audience_versions.py`

**FR:** FR-1.2.4

### P1-A16 Customer feedback intake

**TASK:** Implement manual and file-based feedback intake with validation,
timestamping, store linkage, and PII-conscious rejection messages.

**ACCEPTANCE CRITERIA:**
- Manual text and supported `.csv`, `.txt`, `.xlsx` uploads are accepted up to
  the configured limit and encoding rules.
- A stored feedback item records source, file reference when applicable,
  language, sentiment when supplied, and `captured_at`.
- Rejections identify the file/field and reason without echoing PII.
- Feedback is store-scoped and the PII/consent handling is documented before
  launch.
- Tests cover each accepted format, size/type rejection, and isolation.

**DEPENDS ON:** P1-A7, P1-A14, P1-A4

**TOUCHES:** `src/musawiq/services/feedback.py`,
`src/musawiq/api/feedback.py`,
`src/musawiq/repositories/feedback_items.py`,
`tests/integration/test_feedback.py`

**FR:** FR-1.2.3

### Slice A ordered first wave

The sequence below is dependency-correct. Tasks at the same rank may run in
parallel if the named dependencies are complete.

1. `P1-A1` - scaffold and health (Engineer 2's current work)
2. `P1-A2` - tenant context and scoping
3. `P1-A3` - role matrix and authorization
4. `P1-A4` - audit service
5. `P1-A5` - async jobs and idempotency
6. `P1-A6` - AI governance and degraded mode
7. `P1-A7` - file storage and upload validation
8. `P1-A8` - CSV upload and staged batch
9. `P1-A9` - column mapping
10. `P1-A10` - row validation and dedupe
11. `P1-A11` - preview and error report
12. `P1-A12` - commit, summary, and history
13. `P1-A13` - taxonomy selection (may start after A3 in parallel with A5-A7)
14. `P1-A14` - audience profiles and segments
15. `P1-A15` - profile versioning
16. `P1-A16` - feedback intake (may start after A7/A14)

## Slice B - Concept evaluation

### P1-B1 Product concept draft and validation

**TASK:** Implement create, edit, and draft-save for product concepts with
money, margin, and image validation.

**ACCEPTANCE CRITERIA:**
- Captures name, description, category, optional niche, proposed price, cost,
  currency, and optional image file.
- Required-field and image type/size validation return field-level errors.
- `gross_margin_bp` is computed from price and cost and is displayed; negative
  margin is flagged.
- Concept starts in `draft`, belongs to one store, and records the creator.
- A draft can be reloaded and edited without changing an evaluated row.

**DEPENDS ON:** P1-A2, P1-A3, P1-A7, P1-A13

**TOUCHES:** `src/musawiq/services/concepts.py`,
`src/musawiq/api/concepts.py`, `src/musawiq/domain/money.py`,
`src/musawiq/repositories/product_concepts.py`,
`tests/integration/test_concepts.py`

**FR:** FR-2.1.1

### P1-B2 Concept lifecycle, list, search, and archive

**TASK:** Implement concept listing, filtering, search, archive, and the
hard-delete guard for evaluated concepts.

**ACCEPTANCE CRITERIA:**
- Statuses are exactly `draft`, `evaluated`, `selected`, and `archived`.
- List filters support status, category, and date range; sorting supports latest
  score, category, and created date.
- Search matches name and description within the store.
- Archive is reversible; hard delete is rejected when an evaluation exists.
- Edits use optimistic concurrency via the concept version and return 409 on a
  stale version.

**DEPENDS ON:** P1-B1

**TOUCHES:** `src/musawiq/services/concepts.py`,
`src/musawiq/api/concepts.py`,
`src/musawiq/repositories/product_concepts.py`,
`tests/integration/test_concept_lifecycle.py`

**FR:** FR-2.1.2

### P1-B3 Data sufficiency assessment

**TASK:** Implement the sufficiency engine that evaluates sales history,
audience completeness, price/cost, and optional competitive data.

**ACCEPTANCE CRITERIA:**
- Each input returns exactly one of `available`, `missing`, `stale`, or
  `insufficient`.
- Sales history checks volume and period against configured thresholds; the
  thresholds are documented and versioned in configuration.
- Missing critical inputs block scoring or mark it low-confidence according to a
  documented policy; no critical input is imputed.
- `blocking_reasons` names the exact missing or insufficient input.
- A `sufficiency_checks` row is persisted with the concept and timestamp.

**DEPENDS ON:** P1-B1, P1-A12, P1-A14, P1-A15

**BLOCKED BY:** P1-DEC-15 (sales-history and confidence thresholds)

**TOUCHES:** `src/musawiq/services/sufficiency.py`,
`src/musawiq/repositories/sufficiency_checks.py`,
`src/musawiq/repositories/orders.py`,
`src/musawiq/repositories/audience_profiles.py`,
`tests/integration/test_sufficiency.py`

**FR:** FR-2.1.3

### P1-B4 Versioned scoring model registry and rules-based strategy

**TASK:** Implement the scoring-model registry and a deterministic, rules-based
weighted scoring strategy.

**ACCEPTANCE CRITERIA:**
- A model has `key`, `version`, name, description, weights, parameters, active
  flag, and effective date; `(key, version)` is unique.
- The strategy accepts a concept, input snapshot, and model, and returns score,
  confidence, reliable flag, and factor contributions.
- Identical input snapshots and model version produce identical scores.
- Invalid weights or missing factor definitions are rejected at registration.
- The platform default model version is resolved for a store and recorded with
  each evaluation.

**DEPENDS ON:** P1-B3

**BLOCKED BY:** P1-DEC-16 (default weights and score scale)

**TOUCHES:** `src/musawiq/services/scoring/registry.py`,
`src/musawiq/services/scoring/strategy.py`,
`src/musawiq/domain/scoring.py`,
`src/musawiq/repositories/scoring_models.py`,
`tests/unit/test_scoring_strategy.py`

**FR:** FR-2.1.4

### P1-B5 Evaluation run and batch evaluation job

**TASK:** Implement single and batch evaluation persistence as an async job with
input snapshots and score-unavailable semantics.

**ACCEPTANCE CRITERIA:**
- An evaluation stores concept, model, model version, score (null when
  unavailable), scale, confidence, reliable flag, sufficiency check, input
  snapshot with `schema_version`, and evaluated timestamp.
- Critical missing inputs yield a null score, not zero.
- Batch evaluation accepts multiple concept IDs, reports per-concept results,
  and is idempotent for an unchanged input snapshot plus model version.
- Evaluations are store-scoped and immutable after creation.
- Async progress and failure use the shared job contract.

**DEPENDS ON:** P1-B3, P1-B4, P1-A5

**TOUCHES:** `src/musawiq/services/evaluations.py`,
`src/musawiq/workers/batch_evaluation.py`,
`src/musawiq/repositories/evaluations.py`,
`src/musawiq/api/evaluations.py`, `tests/integration/test_evaluations.py`

**FR:** FR-2.1.4

### P1-B6 Score explanation, factors, and limitations

**TASK:** Implement score-factor generation and the explanation payload with
positive/negative contributions, confidence, limitations, and measured-versus-
inferred labels.

**ACCEPTANCE CRITERIA:**
- Factors store key, label, direction, contribution, explanation, and evidence
  JSONB with `schema_version`.
- The explanation endpoint returns top contributors ranked by absolute
  contribution.
- Confidence and limitations derive from the matching sufficiency check.
- Evidence labels each input as measured or inferred.
- Copy contains no guarantee-of-sales language; a lint test enforces the banned
  phrase list.

**DEPENDS ON:** P1-B5

**TOUCHES:** `src/musawiq/services/scoring/explain.py`,
`src/musawiq/repositories/score_factors.py`,
`src/musawiq/api/evaluations.py`,
`tests/integration/test_score_explanation.py`

**FR:** FR-2.1.5

### P1-B7 Concept comparison, selection, and handoff

**TASK:** Implement side-by-side comparison, filtered sorting, and the audited
selection transition into Stage 2.

**ACCEPTANCE CRITERIA:**
- Comparison returns score, confidence, category, price, margin, and top factors
  for each evaluated concept.
- Only store-owned, evaluated concepts are comparable.
- Selection transitions one or more concepts to `selected`, records actor and
  timestamp in audit, and is idempotent for repeat requests.
- Archived or unevaluated concepts cannot be selected.
- The selected concept ID is returned for the downstream test-creation flow.

**DEPENDS ON:** P1-B2, P1-B5, P1-B6, P1-A4

**TOUCHES:** `src/musawiq/services/concepts_compare.py`,
`src/musawiq/api/concepts.py`,
`src/musawiq/repositories/product_concepts.py`,
`tests/integration/test_concept_compare.py`

**FR:** FR-2.1.6

### P1-B8 E-commerce integration adapter contract and connection lifecycle

**TASK:** Implement the provider-neutral e-commerce adapter contract, OAuth/API
key connection flow, encrypted credential storage, status display, and
disconnect.

**ACCEPTANCE CRITERIA:**
- Adapter interface exposes connect, exchange credentials, revoke, list
  products, and list orders; no provider details leak into services.
- Credentials are encrypted at rest; responses expose only provider, external
  store ID, status, scopes, and last sync time.
- Connection is unique per `(store_id, provider)`; expired/revoked states are
  surfaced before import.
- Disconnect clears tokens, revokes upstream access, stops sync, and sets
  `status = revoked`.
- Contract tests use a fake provider; one real adapter is added only for the
  provider set chosen by D1.

**DEPENDS ON:** P1-A2, P1-A3, P1-A7, P1-A4

**BLOCKED BY:** P1-DEC-6 (D1 platform set)

**TOUCHES:** `src/musawiq/integrations/ecommerce/base.py`,
`src/musawiq/integrations/ecommerce/<provider>.py`,
`src/musawiq/services/connections.py`, `src/musawiq/api/connections.py`,
`tests/integration/test_ecommerce_connection.py`

**FR:** FR-1.1.6, FR-3.2.6 (shared connection foundation)

### P1-B9 Historical import from connected store

**TASK:** Implement the date-range historical import job that maps provider
products and orders into the canonical schema with progress and retry.

**ACCEPTANCE CRITERIA:**
- Merchant selects a date range; the job imports products and orders/order items
  through the same validators and dedupe hash as CSV import.
- Async job reports per-entity progress and partial failures with reasons.
- Retry is safe and does not duplicate products or orders.
- Imported rows carry source connection and batch metadata; imported records are
  deduplicated against CSV imports.
- Disconnect during a run stops further fetching and marks the job cancelled.

**DEPENDS ON:** P1-B8, P1-A5, P1-A10, P1-A12

**BLOCKED BY:** P1-DEC-6 (D1 platform set)

**TOUCHES:** `src/musawiq/workers/integration_sync.py`,
`src/musawiq/services/imports/historical.py`,
`src/musawiq/integrations/ecommerce/`,
`tests/integration/test_historical_import.py`

**FR:** FR-1.1.6

## Slice C - Recommendations and assets

### P1-C1 Recommendation generation job

**TASK:** Implement on-demand recommendation generation with deduplication,
provenance input snapshot, and a configurable result count.

**ACCEPTANCE CRITERIA:**
- Generation uses the store's niche, current audience profile, sales history, and
  trend/competitive data when available; missing sources degrade explicitly.
- A `generation_runs` row stores requested by, model version, input snapshot,
  requested/returned counts, status, error, and timings.
- Returned ideas link to the run, are store-scoped, and are deduplicated against
  existing concepts and dismissed ideas by normalized name plus description.
- The job is async, retry-safe, and reports progress.
- If the AI provider is unavailable, the run fails with a clear reason and no
  fabricated ideas.

**DEPENDS ON:** P1-B1, P1-B2, P1-A14, P1-A15, P1-A5, P1-A6

**BLOCKED BY:** P1-DEC-5 (AI provider), P1-DEC-7 (D3 market/trend source)

**TOUCHES:** `src/musawiq/services/recommendations.py`,
`src/musawiq/workers/recommendation_generation.py`,
`src/musawiq/repositories/generation_runs.py`,
`src/musawiq/repositories/product_ideas.py`,
`tests/integration/test_recommendations.py`

**FR:** FR-2.2.1

### P1-C2 Idea library, save, dismiss, and restore

**TASK:** Implement the idea library list and the save, dismiss-with-reason, and
restore state transitions.

**ACCEPTANCE CRITERIA:**
- States are exactly `new`, `saved`, `dismissed`, and `converted`.
- Save and dismiss are store-scoped; dismissal records the actor and optional
  reason in audit.
- Dismissed ideas are excluded from future generation dedup candidates and
  restore makes them eligible again.
- List filters support state, category, niche, and generation run, with stable
  ordering.
- Cross-store idea access returns 404.

**DEPENDS ON:** P1-C1, P1-A4

**TOUCHES:** `src/musawiq/services/ideas.py`, `src/musawiq/api/ideas.py`,
`src/musawiq/repositories/product_ideas.py`,
`tests/integration/test_idea_library.py`

**FR:** FR-2.2.3

### P1-C3 Evidence provenance and stale-evidence handling

**TASK:** Implement idea evidence with verified versus hypothesis labeling,
source validation, and stale-evidence flags.

**ACCEPTANCE CRITERIA:**
- Evidence stores type `verified` or `hypothesis`, claim, source name, source URL,
  published/retrieved timestamps, and confidence.
- A verified item without a source URL is rejected at the service boundary and
  by the database check.
- Only stored URLs are rendered; the API never synthesizes a link from model
  text.
- Items older than the configured freshness window are marked stale.
- Verified and hypothesis evidence are distinct in the response contract and
  rendered UI treatment.

**DEPENDS ON:** P1-C1

**TOUCHES:** `src/musawiq/services/evidence.py`,
`src/musawiq/repositories/idea_evidence.py`, `src/musawiq/api/ideas.py`,
`tests/integration/test_evidence.py`

**FR:** FR-2.2.2

### P1-C4 Convert idea to product concept

**TASK:** Implement an explicit confirmation flow that converts an idea into a
draft product concept and links both directions.

**ACCEPTANCE CRITERIA:**
- Conversion prefills name, description, category, and niche; price and cost
  remain merchant inputs.
- The concept records `source_idea_id`, and the idea moves to `converted` with
  `converted_concept_id` set in the same transaction.
- A repeat conversion returns the existing concept instead of creating a second.
- Missing merchant-required fields block conversion with specific errors.
- The new concept enters the normal evaluation flow.

**DEPENDS ON:** P1-C1, P1-B1, P1-B2

**TOUCHES:** `src/musawiq/services/ideas_convert.py`,
`src/musawiq/api/ideas.py`,
`src/musawiq/repositories/product_concepts.py`,
`src/musawiq/repositories/product_ideas.py`,
`tests/integration/test_idea_conversion.py`

**FR:** FR-2.2.4

### P1-C5 Test lifecycle and budget envelope

**TASK:** Implement test creation from a selected concept and the explicit test
state transitions used by pages, campaigns, verdicts, and extensions.

**ACCEPTANCE CRITERIA:**
- A draft test records concept, name, primary conversion, currency, total and
  daily budget, planned start/end, and creator.
- Exactly one landing page or post may be attached once the test leaves draft;
  the draft state permits neither.
- Allowed transitions are validated: draft, running, paused, awaiting_verdict,
  completed, extended, cancelled.
- Status changes are audited with actor, timestamp, and before/after values.
- Store scoping and optimistic concurrency are enforced.

**DEPENDS ON:** P1-B7, P1-A3, P1-A4

**TOUCHES:** `src/musawiq/services/tests.py`, `src/musawiq/api/tests.py`,
`src/musawiq/domain/tests.py`, `src/musawiq/repositories/tests.py`,
`tests/integration/test_tests.py`

**FR:** FR-3.2.3, FR-5.1.4 (spec-derived; no FR defines Test CRUD)

### P1-C6 Page template registry and responsive renderer

**TASK:** Seed and expose a versioned page template and render it responsively
with required content slots.

**ACCEPTANCE CRITERIA:**
- A template has key, version, name, active flag, and schema JSONB with
  `schema_version`; `(key, version)` is unique.
- The renderer emits image, name, description, price, CTA, and optional trust
  slots from a page version.
- Rendered HTML passes snapshot tests at mobile and desktop breakpoints.
- Missing required slots fail with a specific error before generation.
- The template contains no inline untrusted HTML; user content is escaped.

**DEPENDS ON:** P1-A1, P1-A2

**TOUCHES:** `src/musawiq/templates/`, `src/musawiq/services/pages/templates.py`,
`src/musawiq/web/public.py`, `src/musawiq/static/`,
`tests/integration/test_page_templates.py`

**FR:** FR-3.1.2

### P1-C7 Landing-page draft, page versions, and autosave

**TASK:** Implement landing-page creation, product/page options, draft
`page_versions`, and debounced autosave.

**ACCEPTANCE CRITERIA:**
- Creation records concept, optional test, unique slug, template, language,
  currency, order method, and draft status.
- Draft content stores image file IDs, copy, price, and generated-by metadata in
  `content` JSONB with `schema_version`.
- Each save creates a new `page_versions` row with incrementing version and
  unique `(landing_page_id, version)`.
- Image type/size validation applies; mandatory fields are checked before
  generation.
- Autosave is debounced and returns the saved version; a conflict returns 409.

**DEPENDS ON:** P1-C6, P1-A7, P1-B1, P1-C5

**TOUCHES:** `src/musawiq/services/pages/drafts.py`,
`src/musawiq/api/pages.py`,
`src/musawiq/repositories/landing_pages.py`,
`src/musawiq/repositories/page_versions.py`,
`tests/integration/test_page_drafts.py`

**FR:** FR-3.1.1

### P1-C8 Product copy generation, claim filter, and RTL editing

**TASK:** Implement copy generation in the selected language and market with a
claim filter, RTL handling, regeneration, and merchant edits.

**ACCEPTANCE CRITERIA:**
- Copy is generated for the selected language and store market; RTL direction is
  applied when the language is RTL.
- A claim filter rejects medical, absolute, and guaranteed-outcome phrasing
  before storage and returns the offending phrase.
- Merchant edits persist in the draft; regeneration requires confirmation and
  does not silently discard edits.
- Generated copy is labeled AI-generated and stores model/template version.
- Tests cover English and Arabic/RTL output, banned phrases, and edit
  persistence.

**DEPENDS ON:** P1-C7, P1-A6

**BLOCKED BY:** P1-DEC-5 (AI provider), P1-DEC-9 (D8 launch languages/markets)

**TOUCHES:** `src/musawiq/services/pages/copy.py`,
`src/musawiq/services/content/claims.py`, `src/musawiq/integrations/ai/`,
`src/musawiq/api/pages.py`, `tests/integration/test_page_copy.py`

**FR:** FR-3.1.3

### P1-C9 Asynchronous page generation

**TASK:** Implement the page-generation job that turns the current draft into a
new AI-generated page version with retry and failure reporting.

**ACCEPTANCE CRITERIA:**
- Generation runs as `job_type = page_generation` with progress and correlation
  ID.
- Success creates a new `page_versions` row with `generated_by = ai` and the
  model version; the draft pointer advances.
- Failure stores a stable error code and message and offers a safe retry without
  duplicating versions.
- Generation completes within the documented P95 <= 5 minute budget in the
  reference environment; the benchmark is recorded.
- Provider-unavailable returns the degraded-mode message from P1-A6.

**DEPENDS ON:** P1-C6, P1-C7, P1-C8, P1-A5, P1-A6

**TOUCHES:** `src/musawiq/workers/page_generation.py`,
`src/musawiq/services/pages/generate.py`,
`src/musawiq/repositories/page_versions.py`,
`tests/integration/test_page_generation.py`

**FR:** FR-3.1.2, FR-0.5

### P1-C10 Order channel configuration and pre-publish verification

**TASK:** Implement WhatsApp and COD order channels with the required XOR and
mechanism validation.

**ACCEPTANCE CRITERIA:**
- Exactly one of landing page or post is attached; type is `whatsapp` or `cod`.
- WhatsApp requires a phone number and prefilled message; the generated link is
  `https://wa.me/{number}?text=...` and includes the attribution token.
- COD requires a form schema; required fields are name, phone, address, quantity,
  and optional variant/notes.
- Selected mechanism is returned in the published page payload.
- A pre-publish check verifies the link opens or the form schema is valid.

**DEPENDS ON:** P1-C7, P1-C15, P1-A2

**BLOCKED BY:** P1-DEC-9 (D8 phone/address markets)

**TOUCHES:** `src/musawiq/services/order_channels.py`,
`src/musawiq/api/pages.py`,
`src/musawiq/repositories/order_channels.py`,
`tests/integration/test_order_channels.py`

**FR:** FR-3.1.4

### P1-C11 Preview, publish, unpublish, and shareable URL

**TASK:** Implement page preview, edit, publish, unpublish, and the live
shareable URL with an accessibility gate.

**ACCEPTANCE CRITERIA:**
- Preview renders desktop and mobile views without publishing.
- Publish requires explicit confirmation and validates mandatory fields,
  template, images, and order channel.
- Publish freezes the current draft as `published_version_id`, sets status and
  timestamp, returns an HTTPS URL, and writes an audit entry.
- Unpublish stops serving content or shows an unavailable state; old versions
  remain in history.
- Accessibility checks cover image alt text, form labels, and contrast and block
  publish on failure.

**DEPENDS ON:** P1-C6, P1-C7, P1-C8, P1-C10, P1-A4

**TOUCHES:** `src/musawiq/services/pages/publish.py`,
`src/musawiq/services/accessibility.py`, `src/musawiq/web/public.py`,
`src/musawiq/api/pages.py`, `tests/e2e/test_page_publish.py`

**FR:** FR-3.1.5

### P1-C12 Ad copy variation generation

**TASK:** Implement generation of distinct ad copy variations with platform
limits, claim filtering, and near-duplicate flags.

**ACCEPTANCE CRITERIA:**
- Generates a configurable number of variations, default 3-5, from product and
  landing-page data in the campaign language.
- Every variation stores headline, body, description, destination, creative
  reference, and draft status.
- Per-provider character limits are enforced and violations are truncated or
  rejected explicitly.
- Near-duplicate variations are flagged by normalized similarity.
- Generated copy passes the same claim filter as page copy and is labeled
  AI-generated.

**DEPENDS ON:** P1-C7, P1-C8, P1-A6

**BLOCKED BY:** P1-DEC-5 (AI provider), P1-DEC-6 (D1 platform set)

**TOUCHES:** `src/musawiq/services/ads/variations.py`,
`src/musawiq/integrations/ads/limits.py`,
`src/musawiq/api/campaigns.py`,
`src/musawiq/repositories/ad_variations.py`,
`tests/integration/test_ad_variations.py`

**FR:** FR-3.2.1

### P1-C13 Ad variation review, approval, and discard

**TASK:** Implement edit, approve, discard, and publication eligibility for ad
variations with audited approval.

**ACCEPTANCE CRITERIA:**
- Only `approved` variations are publication-eligible.
- Edit, approve, and discard transitions are validated and store the actor.
- At least one approved variation is required to proceed; zero returns a
  specific blocking error.
- Approval and discard are audited with before/after status.
- Store scoping prevents acting on another store's variation.

**DEPENDS ON:** P1-C12, P1-A3, P1-A4

**TOUCHES:** `src/musawiq/services/ads/review.py`,
`src/musawiq/api/campaigns.py`,
`src/musawiq/repositories/ad_variations.py`,
`tests/integration/test_ad_review.py`

**FR:** FR-3.2.2

### P1-C14 Campaign and ad set configuration

**TASK:** Implement draft campaign and ad-set configuration with platform,
audience, budget, currency, and schedule validation.

**ACCEPTANCE CRITERIA:**
- Campaign stores test, provider, name, objective, draft status, budget type,
  budget, currency, start/end, and creator.
- Ad set stores campaign, name, status, targeting JSONB with `schema_version`,
  budget type, budget, currency, and schedule.
- Validation covers known provider, minimum budget per provider, `start_at <
  end_at`, required fields, and valid targeting locations/ages.
- Targeting may reference the current audience profile/segments.
- Campaign association is visible on the detail response.

**DEPENDS ON:** P1-C5, P1-B1, P1-A13

**BLOCKED BY:** P1-DEC-6 (D1 platform set)

**TOUCHES:** `src/musawiq/services/campaigns.py`,
`src/musawiq/api/campaigns.py`,
`src/musawiq/repositories/campaigns.py`,
`src/musawiq/repositories/adsets.py`,
`tests/integration/test_campaigns.py`

**FR:** FR-3.2.3

### P1-C15 Tracking link and UTM generation

**TASK:** Implement the tracking-link service that binds a test, campaign, ad
set/variation, and destination to a unique token and UTM parameters.

**ACCEPTANCE CRITERIA:**
- A tracking link has a unique token, test, campaign, optional ad set/variation,
  one of landing page or post, UTM fields, and destination URL.
- Generated URLs contain the token and all non-null UTMs; the token resolves
  server-side.
- Missing or invalid tracking parameters block publication.
- The association is returned on campaign and variation detail responses.
- Links are store-scoped and cannot be modified after creation.

**DEPENDS ON:** P1-C5, P1-C14

**TOUCHES:** `src/musawiq/services/tracking_links.py`,
`src/musawiq/api/tracking_links.py`,
`src/musawiq/repositories/tracking_links.py`,
`tests/integration/test_tracking_links.py`

**FR:** FR-3.2.4

### P1-C16 Campaign pre-flight and ad preview

**TASK:** Implement the itemized pre-flight validation and ad preview for
campaign submission.

**ACCEPTANCE CRITERIA:**
- Pre-flight checks connected and unexpired ad account, at least one approved
  variation, valid budget, published landing page, and valid tracking link.
- Response lists every unresolved item with a stable code and actionable
  message; submission is blocked while any exists.
- Ad preview returns copy, creative, destination URL, and platform for each
  approved variation.
- The same validation result is used by the publish endpoint.
- Tests cover each failing check and the all-green path.

**DEPENDS ON:** P1-C13, P1-C14, P1-C15, P1-C17

**TOUCHES:** `src/musawiq/services/campaigns/preflight.py`,
`src/musawiq/api/campaigns.py`,
`tests/integration/test_campaign_preflight.py`

**FR:** FR-3.2.5

### P1-C17 Advertising account authorization

**TASK:** Implement ad-account OAuth authorization, token refresh, status
display, and disconnect for the chosen provider set.

**ACCEPTANCE CRITERIA:**
- Authorization start returns a provider URL with minimal scopes and a signed
  state value; callback validates state and stores an encrypted connection.
- Tokens refresh before expiry; refresh failure marks the connection expired.
- Connection status, account identity, and last sync time are returned without
  tokens.
- Disconnect revokes the upstream grant and sets status revoked.
- Pre-flight consumes the same status contract.

**DEPENDS ON:** P1-A2, P1-A3, P1-B8, P1-A4

**BLOCKED BY:** P1-DEC-6 (D1 platform set)

**TOUCHES:** `src/musawiq/services/connections/ads.py`,
`src/musawiq/integrations/ads/`, `src/musawiq/api/connections.py`,
`tests/integration/test_ad_connection.py`

**FR:** FR-3.2.6

### P1-C18 Campaign publication and status reporting

**TASK:** Implement idempotent campaign publication through the provider adapter
with request/response snapshots, status mapping, and retry.

**ACCEPTANCE CRITERIA:**
- Publication requires explicit Owner/Manager approval and a passing pre-flight.
- A publication attempt stores target, provider, attempt number, status,
  redacted request/response payloads, error code/message, submitter, and time.
- Success writes the provider campaign/ad-set/ad IDs back to the canonical rows.
- Retry with the same idempotency key returns the existing attempt and never
  creates a duplicate campaign.
- Provider errors map to actionable merchant messages; raw payloads are redacted
  and never contain tokens.

**DEPENDS ON:** P1-C16, P1-C17, P1-A5, P1-A4

**BLOCKED BY:** P1-DEC-6 (D1 platform set)

**TOUCHES:** `src/musawiq/workers/campaign_publish.py`,
`src/musawiq/services/campaigns/publish.py`,
`src/musawiq/repositories/publication_attempts.py`,
`src/musawiq/integrations/ads/`, `tests/integration/test_campaign_publish.py`

**FR:** FR-3.2.7

## Slice D - Measurement

### P1-D1 Event ingestion endpoint and idempotency

**TASK:** Implement the canonical event ingest path with schema validation,
reference checks, and duplicate-ID suppression.

**ACCEPTANCE CRITERIA:**
- Accepts the seven canonical event types and rejects unknown types.
- Requires event ID, store, source, occurred timestamp, and the session or
  product reference required by the event type.
- Duplicate `event_id` inserts are ignored and return the original result.
- Invalid events return a stable reason code and are logged without PII.
- Timing columns are UTC; the store is derived from the authenticated tracking
  context, never trusted from the body.

**DEPENDS ON:** P1-A2, P1-A5, P1-A4, P1-C10

**TOUCHES:** `src/musawiq/api/events.py`,
`src/musawiq/services/tracking/events.py`,
`src/musawiq/repositories/events.py`, `src/musawiq/domain/events.py`,
`tests/integration/test_event_ingest.py`

**FR:** FR-4.1.1

### P1-D2 Tracking session and consent capture

**TASK:** Implement first-party session creation with first-touch UTM capture,
consent state, hashed IP, and last-seen updates.

**ACCEPTANCE CRITERIA:**
- A session records landing page, test, campaign, first-touch UTMs, referrer,
  user agent, IP hash, consent state, start, and last seen.
- Raw IP is never stored; hashing uses the documented salt/key.
- Consent defaults to `unknown`; non-essential events are rejected when consent
  is denied.
- Session cookie is HttpOnly, Secure in production, and scoped to the store.
- Attribution parameters are persisted even when consent is pending.

**DEPENDS ON:** P1-A2, P1-D1, P1-C10

**TOUCHES:** `src/musawiq/services/tracking/sessions.py`,
`src/musawiq/api/tracking.py`,
`src/musawiq/repositories/tracking_sessions.py`,
`tests/integration/test_tracking_sessions.py`

**FR:** FR-4.1.2

### P1-D3 First-party page tracker and bot filtering

**TASK:** Implement the first-party browser tracker for page views and defined
interactions with documented bot filtering.

**ACCEPTANCE CRITERIA:**
- A small first-party script on published pages emits `page_view`,
  `product_view`, `cta_click`, and `cod_form_start` with the session ID.
- Consent is checked before non-essential events are queued or sent.
- Bot filtering applies documented user-agent, rate, and crawler rules and
  excludes bots from metrics.
- Events are queued/retried safely on transient network failure and do not
  duplicate on reload.
- Tests cover normal traffic, a known bot, denied consent, and a failed send.

**DEPENDS ON:** P1-D1, P1-D2, P1-C11

**TOUCHES:** `src/musawiq/static/tracker.js`,
`src/musawiq/services/tracking/bots.py`, `src/musawiq/web/public.py`,
`tests/e2e/test_tracker.py`

**FR:** FR-4.1.2

### P1-D4 WhatsApp tracked redirect and click deduplication

**TASK:** Implement the tracked redirect that resolves a token, records one
WhatsApp click per session window, and forwards to `wa.me`.

**ACCEPTANCE CRITERIA:**
- A valid tracking token 302s to the WhatsApp link with the prefilled message.
- The click event is linked to product, campaign, ad set, and variation when the
  token provides them.
- Duplicate clicks for the same session and product inside the configurable
  window are suppressed.
- An invalid or expired token returns a clear not-found response without leaking
  other tokens.
- WhatsApp clicks never increment order, sale, or confirmed-deposit metrics.

**DEPENDS ON:** P1-D1, P1-D2, P1-C15

**BLOCKED BY:** P1-DEC-8 (D4 attribution defaults)

**TOUCHES:** `src/musawiq/api/redirects.py`,
`src/musawiq/services/tracking/whatsapp.py`,
`src/musawiq/repositories/events.py`,
`tests/integration/test_whatsapp_redirect.py`

**FR:** FR-4.1.3

### P1-D5 COD order form submission

**TASK:** Implement the COD submission endpoint with market-aware validation,
duplicate protection, rate limiting, and transactional order creation.

**ACCEPTANCE CRITERIA:**
- Collects name, phone, address, quantity, and optional variant/notes.
- Phone and address validation follow the target market's rules and return
  field-level errors.
- A valid submission creates a pending COD order with one order item, origin
  `cod`, and test phase `during_test`.
- Duplicate submissions are guarded by `(store_id, dedupe_hash)` and a short
  session/payload window.
- Rate limiting and spam checks reject abusive submissions without echoing PII;
  the address is stored only as ciphertext.

**DEPENDS ON:** P1-D1, P1-D2, P1-C10, P1-A5

**BLOCKED BY:** P1-DEC-9 (D8 markets/phone rules)

**TOUCHES:** `src/musawiq/api/cod.py`,
`src/musawiq/services/orders/cod.py`,
`src/musawiq/domain/validation/phone.py`,
`src/musawiq/services/rate_limit.py`,
`tests/integration/test_cod_orders.py`

**FR:** FR-4.1.4

### P1-D6 Manual deposit verification

**TASK:** Implement the manual deposit path with evidence, pending/confirmed/
rejected states, order linkage, and audited status changes.

**ACCEPTANCE CRITERIA:**
- A deposit is created in pending state with order, test when available, amount,
  currency, and method `manual`.
- Manual confirmation requires a `deposit_evidence` file and records verifier and
  timestamp; rejection records the reason.
- Only confirmed deposits emit `deposit_confirmed` and count toward confirmed
  deposit metrics.
- Every status change is audited with before/after.
- Payment-gateway webhooks and `method = payment_gateway` remain unimplemented
  behind the deferred decision.

**DEPENDS ON:** P1-D5, P1-A7, P1-A4

**TOUCHES:** `src/musawiq/services/deposits.py`,
`src/musawiq/api/deposits.py`,
`src/musawiq/repositories/deposits.py`,
`tests/integration/test_deposits.py`

**FR:** FR-4.1.5

### P1-D7 Attribution resolution and coverage

**TASK:** Implement the versioned single-touch attribution resolver for events
and orders with explicit direct/unknown fallback.

**ACCEPTANCE CRITERIA:**
- Resolver supports the configured model, defaulting to last touch within the
  session plus campaign parameters; first-touch and direct are selectable.
- Unattributed subjects return direct/unknown with `is_attributed = false`; no
  value is guessed.
- The window is store-configurable and recorded with each resolved attribution.
- One attribution row exists per `(subject_type, subject_id)`; re-resolution is
  idempotent.
- Coverage is computed as attributed subjects divided by eligible subjects and
  returned for the dashboard.

**DEPENDS ON:** P1-D1, P1-D2, P1-D3, P1-D5

**BLOCKED BY:** P1-DEC-8 (D4 model and default window)

**TOUCHES:** `src/musawiq/services/attribution/`,
`src/musawiq/domain/attribution.py`,
`src/musawiq/repositories/attributions.py`,
`tests/integration/test_attribution.py`

**FR:** FR-4.1.6

### P1-D8 Conversion metrics dashboard API

**TASK:** Implement the dashboard query service with documented metric
definitions, date/timezone filters, freshness, and sale-label guardrails.

**ACCEPTANCE CRITERIA:**
- Returns visits, WhatsApp clicks, COD submissions, and confirmed deposits
  grouped by product and campaign.
- Every rate includes numerator, denominator, definition, and N/A when the
  denominator is zero.
- Date range and store timezone are selectable; timestamps render in store time.
- Freshness is the latest event `received_at` or metric snapshot time in the
  window.
- The label "sale" is used only for confirmed orders or confirmed deposits; a
  contract test enforces the label policy.
- Dashboard queries stay under P95 < 2 seconds on the Phase 0 baseline.

**DEPENDS ON:** P1-D1, P1-D2, P1-D4, P1-D5, P1-D6, P1-D7

**TOUCHES:** `src/musawiq/services/metrics/dashboard.py`,
`src/musawiq/api/metrics.py`, `src/musawiq/domain/metrics.py`,
`tests/integration/test_metrics_dashboard.py`

**FR:** FR-4.1.7

## Slice E - Decision and investment

### P1-E1 Test result snapshot

**TASK:** Implement the immutable test-result snapshot service that gathers
spend, impressions, clicks, and tracked conversions for a test window.

**ACCEPTANCE CRITERIA:**
- Snapshot records test, period start/end, currency, spend, impressions, clicks,
  tracked conversions, confirmed deposits, conversion rate, cost per conversion,
  completeness, source snapshot IDs, and captured timestamp.
- Spend/impressions/clicks come from metric snapshots; conversions come from the
  test's primary conversion events.
- Missing or partial sources are recorded explicitly with a completeness value;
  nothing is silently zero-filled.
- Timezone and currency match the test/campaign.
- The snapshot is immutable and is the sole input to verdict evaluation.

**DEPENDS ON:** P1-D1, P1-D7, P1-D8, P1-C5

**TOUCHES:** `src/musawiq/services/verdicts/snapshot.py`,
`src/musawiq/repositories/test_result_snapshots.py`,
`tests/integration/test_test_snapshots.py`

**FR:** FR-5.1.1

### P1-E2 Verdict KPI calculation

**TASK:** Implement the verdict KPI calculator with documented formulas and
N/A semantics.

**ACCEPTANCE CRITERIA:**
- Computes conversion rate, cost per tracked conversion, cost per confirmed
  deposit, and total spend.
- Division by zero returns null/N/A, never zero.
- Formula strings are returned with the snapshot and rendered in the verdict
  payload.
- Primary conversion follows the test setting.
- Unit tests cover each zero-denominator and missing-input case.

**DEPENDS ON:** P1-E1

**TOUCHES:** `src/musawiq/services/verdicts/kpis.py`,
`tests/unit/test_verdict_kpis.py`

**FR:** FR-5.1.2

### P1-E3 Decision rule set configuration and resolution

**TASK:** Implement versioned decision-rule sets with per-store/category
resolution, activation, and audited changes.

**ACCEPTANCE CRITERIA:**
- Rule sets store store/category scope, version, active flag, minimum spend,
  clicks, conversions, confirmed deposits, minimum conversion rate, maximum cost
  per conversion, and rules JSONB with `schema_version`.
- Each save creates a new version and deactivates the prior active row.
- Resolution order is category/store then platform default; the selected rule set
  is returned with the verdict.
- Changes are audited with before/after values.
- Unit tests cover resolution precedence and version activation.

**DEPENDS ON:** P1-A3, P1-A4

**BLOCKED BY:** P1-DEC-17 (default rule thresholds)

**TOUCHES:** `src/musawiq/services/decision_rules.py`,
`src/musawiq/api/decision_rules.py`,
`src/musawiq/repositories/decision_rule_sets.py`,
`tests/integration/test_decision_rules.py`

**FR:** FR-5.1.3

### P1-E4 Deterministic verdict evaluation

**TASK:** Implement the deterministic Go/No-Go/Extend Test evaluator with a
sufficiency gate and audited test-state transitions.

**ACCEPTANCE CRITERIA:**
- Outcome is exactly `go`, `no_go`, or `extend_test`; the same snapshot plus rule
  version always yields the same outcome.
- Go/No-Go is impossible when completeness or rule minimums fail; the outcome is
  forced to extend_test.
- Verdict stores snapshot, rule set, outcome, conclusive flag, primary reason,
  limitations, rule trace, and timestamp.
- Rule trace records every threshold, observed value, and pass/fail.
- Test status transitions to awaiting_verdict, completed, or extended according
  to the outcome and is audited.

**DEPENDS ON:** P1-E2, P1-E3, P1-C5

**TOUCHES:** `src/musawiq/services/verdicts/evaluate.py`,
`src/musawiq/domain/verdicts.py`,
`src/musawiq/repositories/verdicts.py`, `src/musawiq/api/verdicts.py`,
`tests/integration/test_verdicts.py`

**FR:** FR-5.1.4

### P1-E5 Inconclusive test detection

**TASK:** Implement explicit inconclusive conditions that route a test to
Extend Test instead of Go/No-Go.

**ACCEPTANCE CRITERIA:**
- Checks insufficient clicks, spend, conversions, confirmed deposits, data
  completeness, attribution coverage, and absence of tracking events.
- The primary reason names the exact failing condition; all triggers are listed
  in limitations.
- An inconclusive result sets `is_conclusive = false` and `outcome =
  extend_test`.
- The evaluator cannot bypass this check through a rule-set override.
- Tests cover each trigger independently and in combination.

**DEPENDS ON:** P1-E1, P1-E3, P1-D7

**TOUCHES:** `src/musawiq/services/verdicts/inconclusive.py`,
`tests/unit/test_inconclusive.py`

**FR:** FR-5.1.6

### P1-E6 Verdict explanation and limitations payload

**TASK:** Implement the verdict explanation payload with met/missed thresholds,
data limitations, evidence-versus-assumption labels, and copy guardrails.

**ACCEPTANCE CRITERIA:**
- Response renders key metrics and each threshold as met or missed with
  observed values.
- Limitations derive from completeness, attribution coverage, and unverified
  COD orders.
- Evidence and assumption sources are distinguishable.
- No guarantee-of-outcome language is allowed; a lint test enforces the banned
  phrase list.
- Prior verdict versions remain readable.

**DEPENDS ON:** P1-E4, P1-E5

**TOUCHES:** `src/musawiq/services/verdicts/explain.py`,
`src/musawiq/api/verdicts.py`, `tests/integration/test_verdict_explanation.py`

**FR:** FR-5.1.5

### P1-E7 Extend a test with budget validation and recomputation policy

**TASK:** Implement test extension with additional budget and duration, budget
cap validation, recorded window, and a documented verdict recomputation policy.

**ACCEPTANCE CRITERIA:**
- Extension stores previous/new end, added budget, currency, reason, and
  approver inside `test_extensions`.
- Additional budget is validated against the test budget and `budget_policies`
  total/daily caps; over-cap requests are rejected.
- Test status becomes `extended` and planned end/total budget advance while
  actuals remain untouched.
- Recompute policy is explicit (combined or new-window) and recorded with the
  new verdict.
- Prior verdicts and snapshots are never modified or deleted.

**DEPENDS ON:** P1-E4, P1-E5, P1-A3, P1-A4

**TOUCHES:** `src/musawiq/services/tests/extend.py`,
`src/musawiq/services/budget_policies.py`,
`src/musawiq/api/tests.py`, `src/musawiq/repositories/test_extensions.py`,
`tests/integration/test_test_extensions.py`

**FR:** FR-5.1.7

### P1-E8 Investment profile inputs and versioning

**TASK:** Implement investment-profile create/update with range, currency, and
missing-value validation and immutable versioning.

**ACCEPTANCE CRITERIA:**
- Captures unit cost, selling price, fulfillment cost, payment fee basis points,
  available budget, target margin, supplier MOQ, lead time, currency, and creator.
- Validation rejects negative amounts, fee/margin outside 0-10000 bp, MOQ < 1,
  negative lead time, and mixed currencies.
- Missing values return an explicit list; nothing is silently defaulted.
- Each save creates a new version, demotes the prior current row, and retains
  history.
- Inputs are store-scoped and linked to a test.

**DEPENDS ON:** P1-C5, P1-A3

**TOUCHES:** `src/musawiq/services/investment/profiles.py`,
`src/musawiq/api/investment.py`,
`src/musawiq/repositories/investment_profiles.py`,
`tests/integration/test_investment_profiles.py`

**FR:** FR-5.2.1

### P1-E9 Demand estimation with stated assumptions

**TASK:** Implement the low/base/high demand estimator with explicit assumptions
and confidence derived from snapshot quality.

**ACCEPTANCE CRITERIA:**
- Produces a low <= base <= high range from the test snapshot and investment
  profile; no single-point output exists.
- Assumptions store traffic source, repeat rate, seasonality factor, and
  attribution adjustment with values and sources, plus `schema_version`.
- Confidence is derived from completeness and sample size; limitations are
  attached.
- Insufficient snapshot data blocks estimation with an explanation rather than
  fabricated numbers.
- Tests cover range ordering, each assumption, and low-confidence output.

**DEPENDS ON:** P1-E1, P1-E8

**TOUCHES:** `src/musawiq/services/investment/demand.py`,
`src/musawiq/repositories/demand_estimates.py`,
`tests/unit/test_demand_estimator.py`

**FR:** FR-5.2.2

### P1-E10 Unit economics calculation

**TASK:** Implement contribution margin, break-even units, and CAC with displayed
formulas and negative-margin flags.

**ACCEPTANCE CRITERIA:**
- Contribution margin = price - cost - fulfillment - payment fee.
- Break-even units = available budget / contribution margin, undefined for a
  non-positive margin and reported as unavailable rather than a number.
- CAC = test spend / tracked conversions, N/A when conversions are zero.
- Formula text is stored in `formulas` JSONB with `schema_version` and returned.
- Negative margin is explicitly flagged in the response; tests cover all edge
  cases.

**DEPENDS ON:** P1-E2, P1-E8, P1-E9

**TOUCHES:** `src/musawiq/services/investment/economics.py`,
`src/musawiq/repositories/unit_economics.py`,
`tests/unit/test_unit_economics.py`

**FR:** FR-5.2.3

### P1-E11 Feasible order quantity scenarios

**TASK:** Implement conservative/base/aggressive scenario generation that
respects MOQ, budget, and the demand range.

**ACCEPTANCE CRITERIA:**
- Derives at least two feasible scenarios when data is sufficient; quantities
  follow the low/base/high demand range.
- Enforces `quantity >= MOQ` and `quantity * unit cost <= available budget`.
- Infeasible scenarios are excluded with a specific reason; when none are
  feasible, returns an explanation and no quantity.
- Scenario rows store inventory cost, expected units sold low/high, revenue and
  profit ranges, sell-through, risk, feasibility, and reason.
- Lead time is surfaced as a constraint note.

**DEPENDS ON:** P1-E8, P1-E9, P1-E10

**TOUCHES:** `src/musawiq/services/investment/scenarios.py`,
`src/musawiq/repositories/quantity_scenarios.py`,
`tests/unit/test_quantity_scenarios.py`

**FR:** FR-5.2.4

### P1-E12 Scenario presentation, risk, and projection labels

**TASK:** Implement the investment recommendation response that presents each
scenario with inventory, revenue/profit ranges, sell-through, and overstock/
stockout risk.

**ACCEPTANCE CRITERIA:**
- Each scenario exposes inventory cost, expected units sold, revenue range,
  profit range, sell-through percentage, overstock risk, and stockout risk.
- Risk derives from expected units low/high versus quantity and is one of
  low/medium/high.
- All estimates are labeled as projections, never guarantees.
- Assumptions are listed from the demand estimate plus scenario notes.
- The response includes no single-point estimate where a range is required.

**DEPENDS ON:** P1-E11

**TOUCHES:** `src/musawiq/services/investment/presentation.py`,
`src/musawiq/api/investment.py`,
`tests/integration/test_investment_presentation.py`

**FR:** FR-5.2.5

### P1-E13 Recalculate with versioning and assumption diff

**TASK:** Implement recalculation of a recommendation with new versions, a
current-row pointer, history, and an assumption diff.

**ACCEPTANCE CRITERIA:**
- Recalculation creates a new `investment_recommendations` version plus fresh
  demand, economics, and scenarios; the prior version is retained and demoted.
- Changing supported assumptions, costs, or budget produces a new version with
  traceable inputs.
- The diff highlights changed assumption fields between versions.
- History lists all versions; the current endpoint returns only the current one.
- Prior recommendation rows are never mutated or deleted.

**DEPENDS ON:** P1-E8, P1-E9, P1-E10, P1-E11, P1-A4

**TOUCHES:** `src/musawiq/services/investment/recalculate.py`,
`src/musawiq/repositories/investment_recommendations.py`,
`src/musawiq/api/investment.py`,
`tests/integration/test_investment_versions.py`

**FR:** FR-5.2.6

## Slice F - Optimization

FR-4.2.1-FR-4.2.4 and FR-4.2.7 execution paths are post-MVP. FR-4.2.5 is the
MVP slice. FR-4.2.6 has no task.

### P1-F1 Scheduled metrics sync

**TASK:** Implement scheduled ad-metric sync with raw and normalized snapshots,
rate limiting, retry, and staleness reporting.

**ACCEPTANCE CRITERIA:**
- Sync runs per connected platform at the configured interval with exponential
  backoff and timeout.
- Raw payload and normalized metrics are stored separately; raw payloads are
  redacted of tokens and PII.
- Rate limits are respected; a failed sync records a stable error and last
  successful time.
- Staleness is exposed per campaign.
- The adapter is provider-neutral and tested with a fake provider.

**DEPENDS ON:** P1-C17, P1-C18, P1-A5

**BLOCKED BY:** P1-DEC-6 (D1 platform set)

**TOUCHES:** `src/musawiq/workers/metric_sync.py`,
`src/musawiq/integrations/ads/metrics.py`,
`src/musawiq/repositories/metric_snapshots.py`,
`tests/integration/test_metric_sync.py`

**FR:** FR-4.2.1

### P1-F2 Campaign KPI calculation

**TASK:** Implement CTR, CPC, CPM, reach, frequency, engagement, spend, and
cost-per-conversion with documented formulas and N/A semantics.

**ACCEPTANCE CRITERIA:**
- Each KPI has a documented numerator, denominator, and formula.
- Unavailable inputs return N/A, not zero.
- Currency and timezone are normalized consistently.
- Calculations are deterministic for a given snapshot.
- Unit tests cover zero denominators and missing values.

**DEPENDS ON:** P1-F1

**TOUCHES:** `src/musawiq/services/optimization/kpis.py`,
`tests/unit/test_campaign_kpis.py`

**FR:** FR-4.2.2

### P1-F3 Optimization thresholds and minimum-data configuration

**TASK:** Implement global and per-campaign threshold configuration with
minimum-data gates and audited versions.

**ACCEPTANCE CRITERIA:**
- Thresholds support global and campaign scope, minimum impressions, clicks, and
  conversions.
- Evaluation returns `insufficient_data` while minimums are unmet.
- Each save creates a version and deactivates the prior active row.
- Changes are audited with before/after values.
- Resolution precedence is campaign, store, then platform default.

**DEPENDS ON:** P1-C14, P1-A3, P1-A4

**BLOCKED BY:** P1-DEC-17 (default thresholds)

**TOUCHES:** `src/musawiq/services/optimization/rules.py`,
`src/musawiq/repositories/optimization_rule_sets.py`,
`tests/integration/test_optimization_rules.py`

**FR:** FR-4.2.3

### P1-F4 Underperformer and promising-ad detection

**TASK:** Implement the finding engine that flags underperforming and promising
ads with reason codes and observed-versus-threshold values.

**ACCEPTANCE CRITERIA:**
- Flags are produced only when minimum data is met.
- Each finding stores campaign/ad set/variation, rule set, status, metric key,
  observed value, threshold value, reason code, window, and evaluated time.
- Underperforming and promising findings use the same rule framework.
- Findings are idempotent for the same snapshot, rule version, and window.
- No flag fires without an explicit threshold.

**DEPENDS ON:** P1-F2, P1-F3

**TOUCHES:** `src/musawiq/services/optimization/findings.py`,
`src/musawiq/repositories/performance_findings.py`,
`tests/integration/test_performance_findings.py`

**FR:** FR-4.2.4

### P1-F5 Optimization recommendations, accept, and dismiss

**TASK:** Implement recommend-only optimization proposals with rationale,
expected impact, budget-cap enforcement, and audited accept/dismiss actions.

**ACCEPTANCE CRITERIA:**
- Generates pause, keep, reallocate, increase-budget, or decrease-budget
  recommendations with rationale and expected impact.
- Recommendations never exceed the active `budget_policies` total or daily cap.
- Merchant can accept or dismiss; accepting records intent only and performs no
  platform write.
- Accept/dismiss is audited with actor and before/after status.
- Store scoping and permission checks apply; pending recommendations expire per
  the configured window.

**DEPENDS ON:** P1-F4, P1-F6, P1-A3, P1-A4

**TOUCHES:** `src/musawiq/services/optimization/recommendations.py`,
`src/musawiq/api/optimization.py`,
`src/musawiq/repositories/optimization_recommendations.py`,
`tests/integration/test_optimization_recommendations.py`

**FR:** FR-4.2.5

### P1-F6 Budget policies, guardrails, and audit

**TASK:** Implement budget-policy administration and the cap/audit guardrails
used by recommendations and test extensions.

**ACCEPTANCE CRITERIA:**
- Policies support test and campaign scope, total cap, optional daily cap,
  currency, enforcement mode, and active flag.
- At least one of test or campaign is required; caps are non-negative and
  currency-consistent.
- A shared checker rejects any proposed change that would exceed the applicable
  cap.
- Every accepted recommendation and extension records reason, before/after,
  timestamp, and actor.
- The kill switch and automated anomaly paths are explicitly absent; a contract
  test asserts no automatic platform write exists.

**DEPENDS ON:** P1-E7, P1-A3, P1-A4

**TOUCHES:** `src/musawiq/services/budget_policies.py`,
`src/musawiq/api/budget_policies.py`,
`src/musawiq/repositories/budget_policies.py`,
`tests/integration/test_budget_policies.py`

**FR:** FR-4.2.7 (guardrails and audit only; execution paths deferred)

## Explicit non-goals

These are carried over from `docs/Requirements.md` and `docs/backlog.md` and are
not Phase 1 work:

- No automated budget reallocation or opt-in automated execution (FR-4.2.6).
- No payment gateway or payment-webhook deposit verification; deposits are
  manual with evidence (D2).
- No multi-touch attribution; only a documented single-touch model with
  direct/unknown fallback (D4).
- No multi-store membership or cross-store collaboration; one store per user for
  MVP (D7).
- No inventory or warehouse sync, mobile apps, real-time streaming optimization,
  or collaboration beyond the Owner/Manager/Analyst roles.
- No kill-switch execution or anomaly-triggered automatic platform writes in
  Phase 1; guardrail checks and audit only (FR-4.2.7 execution paths).
- No admin SPA is assumed by these tasks; see `P1-DEC-10`.

## Deferred and partial FRs

| FR | Status | Reason |
|---|---|---|
| FR-4.2.6 | Not decomposed | Automated execution is an explicit non-goal. The schema stays reserved for Phase 2; do not add platform-write paths. |
| FR-4.2.7 | Partial | P1-F6 implements budget-policy caps and audit for recommendations and extensions. Kill-switch execution and anomaly-triggered actions are deferred. |
| FR-4.1.5 | Partial | P1-D6 implements manual verification with evidence. The payment-gateway webhook path is deferred (D2). |
| FR-4.1.6 | Partial | P1-D7 implements single-touch attribution. Multi-touch is a non-goal. |
| FR-4.2.1-FR-4.2.4 | Post-MVP | Decomposed as P1-F1 to P1-F4, sequenced after the MVP cut. |

## Known decomposition gaps

These are not open product decisions; they are places where the requirements are
silent and a task had to state an explicit assumption. The owner must confirm or
correct them before the named task starts.

1. **Test lifecycle.** No FR defines creating or managing a `Test`, although
   pages, campaigns, verdicts, and extensions all depend on one. P1-C5 covers
   this spec-derived lifecycle. Confirm scope under `P1-DEC-11`.
2. **Authentication and store bootstrap.** No FR covers signup, login, session
   management, or initial store creation. P1-A2 assumes an authenticated tenant
   context exists. Confirm the flow under `P1-DEC-2`.
3. **Admin UI scope.** The FRs describe user-facing screens, but no frontend
   stack or UI ownership is defined. Backend tasks expose HTTP contracts and
   server-rendered public pages. The admin UI split is `P1-DEC-10`.
4. **Public page hosting.** P1-C6/P1-C11 assume this application serves the
   published page and its assets. If a separate site or CDN owns public pages,
   the publish contract must be restated before C11.

## Open decisions

The owner must resolve these before the dependent task starts. No default is
invented here; where the requirements already settle a decision, that is noted.

| ID | Decision needed | Blocks | Settled by requirements? |
|---|---|---|---|
| P1-DEC-1 | Confirm the HTTP framework, ORM, and final scaffold layout. | P1-A1, P1-A2 | No; Engineer 2 scaffold is the starting point |
| P1-DEC-2 | Authentication and store bootstrap: password vs OAuth, session cookie vs bearer token, and how a new user creates a store. | P1-A1, P1-A2, P1-A3 | User fields exist; flow is not specified |
| P1-DEC-3 | File storage backend (local vs object storage), encryption approach, and key management. | P1-A7, P1-A8, P1-A16 | No |
| P1-DEC-4 | Worker runtime: database polling in-process vs a separate worker process/queue. | P1-A5 | Backlog notes DB-backed queue is sufficient for MVP; runtime shape is open |
| P1-DEC-5 | AI provider(s) for copy, recommendations, and scoring assistance, plus fallback behavior. | P1-C1, P1-C8, P1-C12 | No |
| P1-DEC-6 | D1: which ad platforms are in the MVP set. | P1-B8, P1-B9, P1-C12, P1-C14, P1-C17, P1-C18, P1-F1 | No |
| P1-DEC-7 | D3: competitive/trend data source (licensed API, public data, or model knowledge). | P1-C1, P1-C3 | No; degraded mode is required until resolved |
| P1-DEC-8 | D4: single-touch attribution model default and window values. | P1-D4, P1-D7 | Directionally last-touch is suggested; values are open |
| P1-DEC-9 | D8: launch markets, currencies, languages, and RTL set. | P1-C8, P1-C10, P1-D5 | No |
| P1-DEC-10 | Admin frontend stack and whether Phase 1 includes merchant UI or API contracts only. | Acceptance of UI-oriented FR bullets | No |
| P1-DEC-11 | Confirm the Test lifecycle in P1-C5 is in scope despite no FR. | P1-C5 and all downstream test work | No; spec-derived gap |
| P1-DEC-12 | Page-generation reference environment for the P95 <= 5 minute budget. | P1-C9 | No |
| P1-DEC-13 | Upload ceilings and exact MIME allow-lists for CSV, feedback, and images. | P1-A7, P1-A8, P1-A16 | FR gives examples (20 MB) but not final limits |
| P1-DEC-14 | Default recommendation count and near-duplicate similarity threshold. | P1-C1, P1-C12 | FR suggests 3-5 variations; threshold is open |
| P1-DEC-15 | Sales-history volume/period thresholds and the low-confidence policy for sufficiency. | P1-B3 | No; must be documented before build |
| P1-DEC-16 | Default scoring weights, factor definitions, and score scale. | P1-B4 | D6 chooses rules-based, not the weights |
| P1-DEC-17 | Default decision and optimization rule-set values and minimum data. | P1-E3, P1-F3 | No |

## Cross-slice sequencing notes

Slice A is the ordered first wave above. After A is green, the safe order is:

- **B:** B1 -> B2 -> B3 -> B4 -> B5 -> B6 -> B7. B8/B9 may run in parallel once
  D1 is decided.
- **C:** C5 -> C6 -> C7 -> C8 -> C9 -> C11. C14 -> C15 -> C10 -> C11. C12 ->
  C13 -> C16 -> C18. C17 may run parallel to C14. C1-C4 may start once B1/B2 and
  audience versioning are ready.
- **D:** D1 -> D2 -> D3. D4 after D2/C15. D5 -> D6. D7 -> D8.
- **E:** E1 -> E2 -> E3 -> E4 -> E5 -> E6. E7 after E4/E5. E8 -> E9 -> E10 ->
  E11 -> E12 -> E13.
- **F:** F1 -> F2 -> F3 -> F4 -> F5. F6 may be delivered with E7/F5 because it
  owns the shared cap checker.

## Task count

| Slice | Tasks | Notes |
|---|---|---|
| A - Foundation and onboarding | 16 | includes platform foundations and import/audience onboarding |
| B - Concept evaluation | 9 | includes integration import, blocked by D1 |
| C - Recommendations and assets | 18 | includes the spec-derived Test lifecycle |
| D - Measurement | 8 | includes tracking, COD, deposits, attribution, dashboard |
| E - Decision and investment | 13 | includes verdicts, extensions, investment scenarios |
| F - Optimization | 6 | 5 recommendation-path tasks plus budget guardrails |
| **Total** | **70** | 63 of 64 FR headings mapped; FR-4.2.6 intentionally unmapped |

## Definition of ready for a task

Before an engineer starts, all of the following must be true:

- Phase 0 exit gate is green.
- Every `DEPENDS ON` task is accepted.
- Every `BLOCKED BY` decision is resolved or explicitly waived by the owner.
- The required database tables and indexes are accepted; no Phase 1 task creates
  a schema object outside a new, owner-approved DB task.
- The expected API path and response contract are written in the task's first
  commit or in the task description.
- Test fixtures and the target environment for the performance claim exist.

## Definition of done for a task

A task is accepted only when:

- Its acceptance criteria are demonstrated by automated tests or a recorded
  manual check where automation is impossible.
- The task's commit contains code, tests, and any task-owned contract or design
  note.
- `pytest`, lint, and type checks pass for the touched area.
- Tenant-isolation and authorization tests pass for every new endpoint.
- No owner file, unrelated module, or applied migration is modified.
- The owner receives the commit hash and the exact verification output.

