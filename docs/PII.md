# PII Classification Registry (DB-0.18)

Status: **classification authored; scanner in `scripts/pii_scan.py`.** This is the
registry of every column that can hold personal data. The registry dict in the
scanner is the machine-checkable copy; keep the two in sync.

The schema has moved past the original DB-0.18 planning point. The registry
therefore mixes current columns and columns owned by planned tables (`events`,
`tracking_sessions`, `tracking_links`). The scanner reports planned entries as
`SKIPPED`; it does not fail because a future table is absent.

---

## 1. Classes

| Class | Meaning | Examples |
| --- | --- | --- |
| `public` | Safe to expose to unauthenticated readers. | Reference-data names and codes. |
| `internal` | Tenant-confidential but not a direct person identifier. | Model snapshots, prompts, storage keys, checksums. |
| `pii` | Direct identifier with ordinary handling requirements. | `users.email`, `users.full_name`, hashed IP. |
| `sensitive_pii` | High-risk personal data or free text that may contain anything. | Customer name/phone/address, feedback text, raw import rows. |
| `secret` | Credential material; never returned or logged. | Password hashes, OAuth tokens, provider auth config. |

## 2. Protection mechanisms

| Mechanism | Meaning |
| --- | --- |
| `none` | No database-level protection; the column must not carry direct PII. |
| `hash` | One-way hash. `ip_hash` is a salted SHA-256 hex digest; `password_hash` is a password hash. |
| `ciphertext` | Encrypted payload stored in `bytea` or `text`; never `jsonb`. |
| `access-restricted` | Plaintext, but restricted to explicitly authorized roles and tenant-scoped queries. This is not a substitute for encryption where encryption is required. |

Every `*_enc` / `*_encrypted` column must be `bytea` or `text` and classified
`secret` or `sensitive_pii`. The scanner enforces that rule.

## 3. Registry

| Column | Class | Protection | Notes |
| --- | --- | --- | --- |
| `ad_account_connections.access_token_encrypted` | `secret` | `ciphertext` | OAuth access token; ciphertext only. |
| `ad_account_connections.refresh_token_encrypted` | `secret` | `ciphertext` | OAuth refresh token; ciphertext only. |
| `async_jobs.payload` | `sensitive_pii` | `access-restricted` | Job input can embed user-supplied import/generation data. |
| `async_jobs.result` | `sensitive_pii` | `access-restricted` | Job output can embed user-supplied data; never expose to reporting. |
| `audience_profiles.notes` | `internal` | `access-restricted` | Free text; may include customer observations. |
| `audit_logs.after` | `sensitive_pii` | `access-restricted` | JSONB snapshot can contain order/user data. |
| `audit_logs.before` | `sensitive_pii` | `access-restricted` | JSONB snapshot can contain order/user data. |
| `audit_logs.ip_hash` | `pii` | `hash` | Hashed request address; raw address is never stored. |
| `audit_logs.metadata` | `sensitive_pii` | `access-restricted` | Free-form audit metadata; may carry identifiers. |
| `content_generation_jobs.negative_prompt` | `internal` | `access-restricted` | User-supplied generation text. |
| `content_generation_jobs.prompt` | `internal` | `access-restricted` | User-supplied generation text. |
| `content_providers.auth_config_encrypted` | `secret` | `ciphertext` | Provider credentials; ciphertext only. |
| `evaluations.input_snapshot` | `internal` | `access-restricted` | Audience/context snapshot; no direct customer identifiers. |
| `events.ip_hash` | `pii` | `hash` | Planned table; hashed address only. |
| `events.properties` | `sensitive_pii` | `access-restricted` | Planned table; event payload can contain form data. |
| `events.referrer` | `internal` | `access-restricted` | Planned table; URLs can carry query parameters. |
| `events.url` | `internal` | `access-restricted` | Planned table; URLs can carry query parameters. |
| `feedback_items.text` | `sensitive_pii` | `access-restricted` | Free-text feedback can contain any customer detail. |
| `generation_runs.input_snapshot` | `internal` | `access-restricted` | Recommendation input snapshot; treat as tenant-confidential. |
| `import_issues.message` | `sensitive_pii` | `access-restricted` | Validation messages may echo raw row values. |
| `import_issues.raw_value` | `sensitive_pii` | `access-restricted` | Rejected field value from an imported file. |
| `import_rows.normalized_data` | `sensitive_pii` | `access-restricted` | Normalized imported row; may contain customer details. |
| `import_rows.raw_data` | `sensitive_pii` | `access-restricted` | Raw imported row; may contain customer details. |
| `order_channels.whatsapp_number` | `sensitive_pii` | `access-restricted` | Business contact number; restrict to tenant readers. |
| `orders.customer_address_enc` | `sensitive_pii` | `ciphertext` | Encrypted delivery address. |
| `orders.customer_name` | `sensitive_pii` | `access-restricted` | Plaintext in DB-0.5; encrypt or keep behind restricted access. |
| `orders.customer_phone` | `sensitive_pii` | `access-restricted` | Plaintext in DB-0.5; encrypt or keep behind restricted access. |
| `product_ideas.rationale` | `internal` | `none` | Model-generated rationale; may quote user context, no direct identifiers. |
| `store_connections.access_token_encrypted` | `secret` | `ciphertext` | OAuth access token; ciphertext only. |
| `store_connections.refresh_token_encrypted` | `secret` | `ciphertext` | OAuth refresh token; ciphertext only. |
| `stored_files.checksum_sha256` | `internal` | `none` | Content checksum; not reversible and not a PII locator. |
| `stored_files.metadata` | `internal` | `access-restricted` | Uploader-supplied metadata; review before exposing. |
| `stored_files.original_filename` | `sensitive_pii` | `access-restricted` | Filenames can contain customer names or document titles. |
| `stored_files.storage_key` | `internal` | `access-restricted` | Object-store locator; never expose to clients. |
| `tracking_links.token` | `internal` | `none` | Planned table; public attribution token, not a user credential. |
| `tracking_sessions.ip_hash` | `pii` | `hash` | Planned table; hashed address only. |
| `tracking_sessions.referrer` | `internal` | `access-restricted` | Planned table; URLs can carry query parameters. |
| `tracking_sessions.user_agent` | `internal` | `access-restricted` | Planned table; browser fingerprint may aid re-identification. |
| `users.auth_subject` | `sensitive_pii` | `access-restricted` | External identity subject; linkable identifier. |
| `users.email` | `pii` | `access-restricted` | Account identifier; citext, unique. |
| `users.full_name` | `pii` | `access-restricted` | Direct identifier. |
| `users.password_hash` | `secret` | `hash` | One-way credential hash; never log or return. |
| `users.phone` | `pii` | `access-restricted` | Direct contact identifier. |

## 4. Required controls

- **No raw IP addresses.** The only address columns are `ip_hash char(64)` on
  `audit_logs`, `events`, and `tracking_sessions`. The scanner fails if any
  column named `ip_address` appears.
- **Ciphertext is never stored in `jsonb`.** Encrypted token and address
  payloads use `text` or `bytea`.
- **Free text is access-restricted.** `feedback_items.text`,
  `stored_files.original_filename`, `audience_profiles.notes`, and the import
  staging text are not exposed to the reporting role.
- **JSONB snapshots are treated as sensitive.** `audit_logs.before/after/
  metadata`, import row/issue payloads, async job payloads, and event properties
  can all carry user data. They carry a `schema_version` as required by the
  conventions.
- **Credentials never leave the database.** `password_hash`, OAuth tokens, and
  provider auth configuration are `secret` and must not be logged or returned
  by APIs.
- **Reporting is not granted on PII tables.** The reporting role excludes
  `users`, `orders`, `order_items`, `audit_logs`, `stored_files`, and
  `feedback_items`.

## 5. Gaps and unresolved classifications

- `orders.customer_name` and `orders.customer_phone` are **plaintext** in the
  current DB-0.5 migration. They are classified `sensitive_pii` with
  `access-restricted`, not `ciphertext`, because no encryption exists yet. DB-0.18
  must either add encryption or explicitly accept restricted-access handling.
- `feedback_items.text` and `stored_files.original_filename` are sensitive but
  plaintext; they rely on role/RLS access restriction. Do not expose them to
  reporting or analytics exports.
- `product_ideas.rationale` is classified `internal`, per the task guidance. It
  may quote user context but should not contain direct identifiers; if it starts
  carrying customer text, reclassify it as `sensitive_pii`.
- `stored_files.checksum_sha256` is `internal`: a content checksum is not a
  reversible identifier, but it should not be used as a public file locator.
- `async_jobs.payload` / `result` are classified `sensitive_pii`
  conservatively. Many jobs contain only IDs; import and generation jobs can
  contain user text.
- `tracking_links.token` is `internal`: it is a public attribution token, not a
  user credential. It still matches the `token` heuristic, so it must remain in
  the registry.
- `order_channels.whatsapp_number` is `sensitive_pii`: it is a business contact
  number and should be tenant-scoped.

## 6. Scanner

```powershell
# Fresh migrated scratch database (default)
.venv\Scripts\python.exe -m scripts.pii_scan --scratch

# Existing migrated database
.venv\Scripts\python.exe -m scripts.pii_scan --url $env:MUSAWIQ_TEST_DATABASE_URL

# Machine-readable
.venv\Scripts\python.exe -m scripts.pii_scan --scratch --json
```

The scanner reports `PASS`, `FAIL`, or `SKIPPED` and exits 1 only on `FAIL`.
Checks:

1. every column matching the PII heuristics (`email`, `phone`, `full_name`,
   `name` on user-ish tables, `address`, `ip_address`, `ip_hash`, `password`,
   `secret`, `token`, `auth_subject`) is in the registry. Timestamp metadata
   ending in `_at` (for example `token_expires_at`, `email_verified_at`) is
   excluded: it records when something happened, not the identifier itself;
2. every `*_enc` / `*_encrypted` column is `bytea`/`text` and classified
   `secret` or `sensitive_pii`;
3. no column named `ip_address` exists anywhere.

Planned registry entries whose tables do not exist yet are reported as
`SKIPPED`, not `FAIL`.

## 7. Keeping the registry in sync

`scripts/pii_scan.py` contains `REGISTRY_ROWS`, the machine-checkable copy of
the table above. `tests/tools/test_pii_scan.py` verifies every registry key is
documented. When a new column or table is added:

1. classify it here;
2. add the same row to `REGISTRY_ROWS`;
3. run the scanner and the tool tests.
