# Development Seed Guide (DB-0.20)

`scripts/seed_dev.py` creates a deterministic, idempotent development fixture set.
It is for local development and demo databases only.

## 1. Safety guard

The seed refuses to run unless both conditions hold:

```text
MUSAWIQ_SEED_ENV=development
MUSAWIQ_APP_ENV is unset or is not "production" (case-insensitive)
```

If either check fails it prints `REFUSED: ...` to stderr and exits `1` before
opening a database connection. The guard is checked twice: once in the CLI entry
point and once inside `seed_database()` so an import cannot bypass it.

## 2. What the seed creates

Every row has a fixed UUID and is inserted with `ON CONFLICT DO NOTHING`.

| Table | Rows | Content |
| --- | --- | --- |
| `users` | 3 | `owner@dev.musawiq.local` / manager / analyst, all `status='active'`, with the matching `role`. No password hashes or auth subjects are seeded. |
| `stores` | 1 | `dev-store`, owned by the owner user, `SA` / `SAR` / `ar`, `Asia/Riyadh`, onboarding completed. |
| `categories` | 2 | A small tree: `home-kitchen` and child `kitchen-gadgets`. |
| `niches` | 2 | One global `coffee-tea` niche and one store-specific `home-barista` niche. |
| `scoring_models` | 2 | Platform default (`store_id NULL`, key `default`, v1) and store model (`dev-store`, v1). |
| `decision_rule_sets` | 1 when present | Platform default (`store_id NULL`, category `NULL`, v1). Skipped at the current head because the table does not exist yet. |
| `optimization_rule_sets` | 1 when present | Global default (`store_id NULL`, scope `global`, v1). Skipped at the current head because the table does not exist yet. |
| `audience_profiles` | 1 | Current v1 profile for `dev-store`, both niches, Arabic. |
| `audience_segments` | 2 | `Young Professionals` (Riyadh, 25-40) and `Families` (Jeddah, 30-50). |

The seed relies on the reference rows installed by DB-0.3 (`SA`, `SAR`, `ar`).

The store-specific scoring model uses key `dev-store`, not `default`, because the
current uniqueness rule is `(key, version)`; two rows with key `default` and
version `1` cannot coexist.

### Fixed UUIDs

| Object | UUID |
| --- | --- |
| Owner user | `11111111-1111-4111-8111-111111111111` |
| Manager user | `22222222-2222-4222-8222-222222222222` |
| Analyst user | `33333333-3333-4333-8333-333333333333` |
| Store | `44444444-4444-4444-8444-444444444444` |
| Category root | `55555555-5555-4555-8555-555555555551` |
| Category child | `55555555-5555-4555-8555-555555555552` |
| Global niche | `66666666-6666-4666-8666-666666666661` |
| Store niche | `66666666-6666-4666-8666-666666666662` |
| Platform scoring model | `77777777-7777-4777-8777-777777777771` |
| Store scoring model | `77777777-7777-4777-8777-777777777772` |
| Platform decision rule set | `88888888-8888-4888-8888-888888888881` |
| Global optimization rule set | `99999999-9999-4999-8999-999999999991` |
| Audience profile | `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1` |
| Segment: professionals | `bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1` |
| Segment: families | `bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2` |

## 3. Running it

```powershell
$env:MUSAWIQ_SEED_ENV = "development"
$env:MUSAWIQ_APP_ENV = "development"

# Disposable database: migrate, seed, report, drop
.venv\Scripts\python.exe -m scripts.seed_dev --scratch

# Existing migrated development database
.venv\Scripts\python.exe -m scripts.seed_dev --url $env:MUSAWIQ_DATABASE_URL
```

The default mode is `--scratch`. Scratch mode uses
`MUSAWIQ_ADMIN_DATABASE_URL` to create a uniquely named throwaway database, runs
`alembic upgrade head`, seeds it, and drops it.

Example summary:

```text
SEED SUMMARY
Item                          Inserted   Skipped  Note
------------------------------------------------------------------------------
users                                3         0
stores                               1         0
categories                           2         0
niches                               2         0
scoring_models                       2         0
decision_rule_sets                   0         0  SKIPPED: table not present at this head
optimization_rule_sets               0         0  SKIPPED: table not present at this head
audience_profiles                    1         0
audience_segments                    2         0
------------------------------------------------------------------------------
TOTAL                               13         0
```

A second run reports `TOTAL 0 13` (everything skipped) and leaves row counts
unchanged.

## 4. Current-head limitation

At head `0011` the `decision_rule_sets` and `optimization_rule_sets` tables do
not exist yet (DB-0.11/DB-0.12). The seed checks `to_regclass()` and reports those
two rows as `SKIPPED` rather than failing. Rerun the seed after those migrations
land; the inserts are already written against the specification columns.

If a future migration changes those columns, the conditional insert is the place
to update. Until then the seed is green on the current head.

## 5. Reset

For a disposable database, prefer `--scratch`.

To rebuild an existing development database from empty:

```powershell
$env:MUSAWIQ_SEED_ENV = "development"
$env:MUSAWIQ_APP_ENV = "development"

.venv\Scripts\python.exe -m alembic downgrade base
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m scripts.seed_dev --url $env:MUSAWIQ_DATABASE_URL
```

This is destructive. It must never be run against production or a database that
contains real merchant data.

## 6. What the seed must never contain

- Production data or exports from a real store.
- Real personal data, customer names, phone numbers, addresses, or emails.
- Credentials, API keys, OAuth tokens, or password hashes.
- Provider secrets or any value that looks like a real secret.

The seed uses `@dev.musawiq.local` addresses, `Dev Owner` style names, fixed
development UUIDs, and no authentication material. The PII classification in
`docs/PII.md` still applies to the dev rows; they are fake data, not a waiver.

## 7. Tests

```powershell
.venv\Scripts\python.exe -m pytest tests/tools/test_seed_dev.py -q
```

The tests provision a scratch database, run the seed twice, compare row counts,
verify the owner/store uniqueness, and confirm the two refusal guards (missing
`MUSAWIQ_SEED_ENV`, and `MUSAWIQ_APP_ENV=production`).
