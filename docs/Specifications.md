# Specifications

## Domain Entities

### Identity & Tenancy
- **Store**: Tenant boundary that owns all merchant data.
- **User**: Person who signs in and acts on a store.
- **AuditLog**: Append-only record of consequential actions with actor, target, and before/after values.
- **AsyncJob**: Background work record for imports, syncs, generation, and publication, including state and idempotency key.

### Integrations & Data Ingestion
- **StoreConnection**: Authorized e-commerce integration credentials and connection status.
- **AdAccountConnection**: Authorized ad-platform credentials, scopes, and refresh state.
- **ContentProvider**: AI/media generation provider configuration for images and videos.
- **ContentGenerationJob**: Tracks an image/video generation request and its produced creatives.
- **StoredFile**: Metadata and storage reference for uploaded files such as CSVs, feedback, images, and AI-generated media.
- **ImportBatch**: One import run with source, status, record counts, and date range.
- **ColumnMapping**: Saved source-column to canonical-field mapping for a store.
- **ImportRow**: Staged upload row with its validation outcome.
- **ImportIssue**: Row- or field-level validation failure with reason and raw value.
- **Product**: Canonical catalog product derived from imported or live data.
- **Order**: Unified order from either an imported history or a COD submission, tagged as before, during, or after its test.
- **OrderItem**: Product line within an order, holding product, quantity, and amount.

### Audience & Store Context
- **Category**: Taxonomy node describing the store's market.
- **Niche**: Curated or custom specialization within a category.
- **AudienceProfile**: Versioned target-audience definition for a store.
- **AudienceSegment**: One location, age, or interest segment under an audience profile.
- **FeedbackItem**: Customer feedback entry with source and timestamp.

### Product Evaluation
- **ProductConcept**: Candidate product submitted for viability assessment.
- **SufficiencyCheck**: Per-input data availability result for a concept.
- **Evaluation**: One scoring run with score, model version, and input snapshot.
- **ScoreFactor**: Positive or negative contribution explaining an evaluation.
- **ScoringModel**: Versioned scoring rules and weights.

### Recommendations
- **GenerationRun**: Metadata for one recommendation-generation request.
- **ProductIdea**: AI-suggested product with rationale and lifecycle state.
- **IdeaEvidence**: Supporting item tagged as Verified or AI Hypothesis.

### Assets, Campaigns & Tests
- **LandingPage**: Product-test page with slug, publish state, and order method.
- **PageVersion**: Immutable draft or published snapshot of page content.
- **PageTemplate**: Versioned responsive layout used to generate pages.
- **OrderChannel**: WhatsApp or COD configuration attached to a landing page or post.
- **Post**: Social/native post attached to a test that contains text content and creatives.
- **PostCreative**: Join between Post and Creative with ordering.
- **Creative**: Reusable image, video, or GIF asset (uploaded or AI generated) with variants tracked.
- **CreativeVariant**: Media variant (aspect ratio/size/quality) linked to a creative.
- **Test**: Central product test linking concept, landing page or post, campaigns, budget, and time window.
- **TestExtension**: Additional budget and duration applied to an inconclusive test.
- **Campaign**: Ad campaign with platform, objective, budget, dates, and status.
- **AdSet**: Targeting and budget grouping inside a campaign that contains ads.
- **AdVariation**: Ad creative or copy variation with approval state and platform mapping.
- **TrackingLink**: UTM or click token tying a destination to product, page, post, and campaign.
- **PublicationAttempt**: Campaign submission attempt with platform ID, status, and mapped errors.

### Measurement
- **TrackingSession**: Visitor session with first-touch parameters and consent state.
- **Event**: Typed behavioral event such as page view, click, form start, order, or deposit.
- **Deposit**: Pre-order deposit with pending, confirmed, or rejected state.
- **Attribution**: Resolved attribution model, version, and window for an event or order.
- **MetricSnapshot**: Raw and normalized campaign and ad-set metrics captured per sync.

### Optimization
- **OptimizationRuleSet**: Versioned thresholds and minimum-data rules for optimization.
- **PerformanceFinding**: Flagged ad or ad set with metric, observed value, threshold, and reason.
- **OptimizationRecommendation**: Proposed pause, keep, or reallocate action with rationale.
- **OptimizationAction**: Executed change with before/after values, actor, timestamp, and reversal reference.
- **BudgetPolicy**: Hard total and daily caps governing automated changes.
- **Alert**: Anomaly, overspend, or sync-failure notification.

### Decision & Investment
- **DecisionRuleSet**: Versioned Go, No-Go, and Extend Test thresholds.
- **TestResultSnapshot**: Frozen metrics used to produce a verdict.
- **Verdict**: Go, No-Go, or Extend Test outcome with rule version and input references.
- **InvestmentProfile**: Versioned cost, price, budget, MOQ, and lead-time inputs.
- **InvestmentRecommendation**: Versioned computed output root that owns the demand estimate, unit economics, and quantity scenarios.
- **DemandEstimate**: Low, base, and high demand projection with stated assumptions, attached to an investment recommendation.
- **UnitEconomics**: Contribution margin, break-even units, and customer acquisition cost, attached to an investment recommendation.
- **QuantityScenario**: Proposed order quantity with cost, revenue, profit, and risk figures, attached to an investment recommendation.

### Reference Data
- **Country/Region, Currency, Language, AdPlatform, EventType, Status enums**: Controlled vocabularies used across the domain.

## Entity Fields

### Conventions

- **Database:** PostgreSQL.
- **Physical naming:** entity names in this document are singular (`Order`, `User`), but physical tables are **plural snake_case** (`orders`, `users`) to avoid reserved-word quoting. Irregular plurals: `country`→`countries`, `currency`→`currencies`, `category`→`categories`, `budget_policy`→`budget_policies`.
- **Keys:** `id uuid` (UUIDv7) primary key on every entity. **Exception:** reference tables (`countries`, `currencies`, `languages`, `ad_platforms`, `event_types`) use the natural `code` column as the primary key and carry no `id` or timestamps.
- **Timestamps:** `created_at timestamptz`, `updated_at timestamptz` on mutable entities; append-only tables have `created_at` only.
- **Tenancy:** every tenant-owned table carries `store_id uuid NOT NULL` even when derivable, for row-level security, partitioning, and index efficiency. **Exception:** `store` is the tenant root and carries no `store_id`.
- **Platform-global rows:** `content_provider`, `niche`, `scoring_model`, `optimization_rule_set`, `decision_rule_set`, `async_job`, and `audit_log` allow a nullable `store_id` to represent platform defaults or system-wide actions.
- **Money:** `*_minor bigint` (minor units) + `currency char(3)` (ISO 4217).
- **Rates:** stored as basis points (`*_bp int`) for inputs; computed metrics as `numeric(12,6)`.
- **Enums:** `text` + `CHECK` (portable); values listed inline.
- **Flexible data:** `jsonb` only for configuration, platform payloads, and snapshots; fields used in filters and dashboards are promoted to columns.
- **Soft delete:** `deleted_at` only on user-visible entities; audit and event tables are append-only.
- **Concurrency:** `version int` on mutable aggregates; `UNIQUE` constraints noted inline.
- **PII at rest:** encrypted payloads use `bytea` ciphertext columns (e.g., `customer_address_enc`), never `jsonb`. No raw IP is stored; only `ip_hash char(64)`.
- **NULL-safe uniqueness:** every `UNIQUE` constraint that includes a nullable column is declared `NULLS NOT DISTINCT` so rows with NULLs cannot duplicate.
- **Integrity exceptions (application-enforced, no FK):**
  - Array reference columns (`niche_ids uuid[]`, `image_file_ids uuid[]`, `result_creative_ids uuid[]`, `source_metric_snapshot_ids uuid[]`, `scopes text[]`, `media_types text[]`).
  - Polymorphic references (`audit_log.target_id`, `attribution.subject_id`).
  - Circular reference pairs (`test`↔`landing_page`, `test`↔`post`, `landing_page.current_version_id`↔`page_version.landing_page_id`, `product_concept.source_idea_id`↔`product_idea.converted_concept_id`) are added after both tables exist; nullable columns make this safe without deferrable constraints.
- **Partitioning:** `id uuid` remains the primary key in MVP. Partitioning `event`, `order`, and `metric_snapshot` later requires the partition key in the PK; the exact `ALTER` plan is recorded in the DB-0.16 task.

`Base` below means `id, created_at, updated_at`. `Tenant base` means `Base + store_id`.

---

### Identity & Tenancy

**Store** - Tenant root.
- `owner_user_id uuid` FK to User, UNIQUE (MVP 1 store per user)
- `name text`
- `slug text` UNIQUE
- `status text` - `active | suspended | closed`
- `default_currency char(3)`
- `default_language text`
- `timezone text` (IANA)
- `country_code char(2)`
- `onboarding_status text` - `not_started | in_progress | completed`
- `settings jsonb`
- `deleted_at timestamptz`
- `Base` applies; no `store_id` (this is the tenant).

**User** - Authenticated actor.
- `email citext` UNIQUE
- `password_hash text` NULL (null for OAuth-only)
- `full_name text`
- `phone text` NULL
- `locale text`
- `timezone text`
- `role text` - `owner | manager | analyst` (MVP; see scalability note)
- `status text` - `invited | active | disabled`
- `email_verified_at timestamptz`
- `last_login_at timestamptz`
- `auth_provider text` NULL - `password | google | ...`
- `auth_subject text` NULL
- `deleted_at timestamptz`
- UNIQUE (`auth_provider`, `auth_subject`) where not null
- `Base` applies.

**AuditLog** - Immutable action record.
- `store_id uuid` NULL (system-wide actions)
- `actor_user_id uuid` NULL
- `actor_type text` - `user | system | service`
- `action text` (e.g., `import.committed`, `campaign.published`)
- `target_type text`
- `target_id uuid`
- `before jsonb`
- `after jsonb`
- `metadata jsonb`
- `ip_hash char(64)` (no raw IP)
- `user_agent text`
- `correlation_id uuid`
- `Base` minus `updated_at`.

**AsyncJob** - Background work.
- `store_id uuid` NULL
- `job_type text` - `import | integration_sync | page_generation | ad_publication | metric_sync | recommendation_generation | content_generation`
- `state text` - `queued | running | succeeded | failed | partial | cancelled`
- `idempotency_key text` UNIQUE where not null
- `payload jsonb`
- `result jsonb`
- `progress_current int`, `progress_total int`
- `attempt_count int`, `max_attempts int`
- `error_code text`, `error_message text`
- `correlation_id uuid`
- `scheduled_at`, `started_at`, `finished_at timestamptz`
- `Base` with nullable `store_id`.

---

### Integrations & Data Ingestion

**StoreConnection** - E-commerce platform authorization.
- `provider text` - `shopify | woocommerce | salla | zid | ...`
- `external_store_id text`
- `status text` - `connected | expired | revoked | error`
- `scopes text[]`
- `access_token_encrypted text`
- `refresh_token_encrypted text`
- `token_expires_at timestamptz`
- `last_synced_at timestamptz`
- `metadata jsonb`
- UNIQUE (`store_id`, `provider`)
- Tenant base.

**AdAccountConnection** - Ad platform authorization.
- `provider text` - `meta | tiktok | google | snapchat`
- `external_account_id text`
- `account_name text`
- `status text` - `connected | expired | revoked | error`
- `scopes text[]`
- `access_token_encrypted text`
- `refresh_token_encrypted text`
- `token_expires_at timestamptz`
- `last_synced_at timestamptz`
- `metadata jsonb`
- UNIQUE (`store_id`, `provider`, `external_account_id`)
- Tenant base.

**ContentProvider** - AI/media generation provider.
- `store_id uuid` NULL (null means platform default provider)
- `code text`
- `name text`
- `media_types text[]` - `image|video|gif`
- `auth_config_encrypted text`
- `rate_limits jsonb`
- `pricing jsonb`
- `capabilities jsonb`
- `enabled boolean`
- `is_default boolean`
- UNIQUE (`store_id`, `code`); UNIQUE (`code`) where `store_id` is null
- `Base` with nullable `store_id`.

**ContentGenerationJob** - Image/video generation request.
- `content_provider_id uuid`
- `type text` - `image|video`
- `prompt text`
- `negative_prompt text` NULL
- `params jsonb` - aspect_ratio, duration_ms, fps, seed, style, etc.
- `status text` - `queued|running|succeeded|failed|cancelled`
- `requested_by uuid`
- `result_creative_ids uuid[]`
- `cost_minor bigint` NULL
- `currency char(3)` NULL
- `error_code text` NULL
- `error_message text` NULL
- `async_job_id uuid` NULL
- `started_at timestamptz` NULL
- `finished_at timestamptz` NULL
- Tenant base minus `updated_at`.

**StoredFile** - Uploaded asset metadata.
- `purpose text` - `sales_csv | feedback_file | product_image | ad_creative | deposit_evidence | ai_image | ai_video | creative`
- `original_filename text`
- `mime_type text`
- `size_bytes bigint`
- `checksum_sha256 char(64)`
- `storage_provider text`
- `storage_key text`
- `status text` - `staged | committed | deleted`
- `uploaded_by_user_id uuid` NULL
- `metadata jsonb`
- `deleted_at timestamptz`
- Tenant base minus `updated_at`.

**ImportBatch** - One import run.
- `source_type text` - `csv | store_connection`
- `stored_file_id uuid` NULL
- `store_connection_id uuid` NULL
- `column_mapping_id uuid` NULL
- `status text` - `uploaded | mapping | validating | preview | committing | completed | failed | cancelled`
- `strict_mode boolean`
- `date_range_start date`, `date_range_end date`
- `total_rows int`, `valid_rows int`, `invalid_rows int`, `duplicate_rows int`, `imported_rows int`, `skipped_rows int`
- `error_report_file_id uuid` NULL
- `started_at timestamptz`, `completed_at timestamptz`
- `created_by uuid`
- CHECK (`source_type = 'csv'` requires `stored_file_id`; `store_connection` requires `store_connection_id`)
- Tenant base.

**ColumnMapping** - Reusable field mapping.
- `name text`
- `source_type text`
- `mapping jsonb` - `{ target_field: source_column }`
- `is_default boolean`
- `created_by uuid`
- Tenant base.

**ImportRow** - Staged row (transient; purgeable).
- `import_batch_id uuid`
- `row_number int`
- `raw_data jsonb`
- `normalized_data jsonb`
- `status text` - `valid | invalid | duplicate | imported | skipped`
- `issue_count int`
- `created_order_id uuid` NULL
- UNIQUE (`import_batch_id`, `row_number`)
- Tenant base minus `updated_at`.

**ImportIssue** - Row or field validation error.
- `import_batch_id uuid`
- `import_row_id uuid` NULL
- `row_number int`
- `field_name text` NULL
- `issue_code text`
- `severity text` - `error | warning`
- `message text`
- `raw_value text`
- Tenant base minus `updated_at`.

**Product** - Canonical catalog product.
- `external_product_id text` NULL
- `sku text` NULL
- `name text`
- `description text`
- `category_id uuid` NULL
- `currency char(3)`
- `cost_minor bigint` NULL
- `price_minor bigint` NULL
- `image_file_id uuid` NULL
- `status text` - `active | archived`
- `source text` - `imported | manual | concept`
- `metadata jsonb`
- `deleted_at timestamptz`
- UNIQUE (`store_id`, `external_product_id`) where not null; UNIQUE (`store_id`, `sku`) where not null
- Tenant base.

**Order** - Unified imported or COD order.
- `origin text` - `imported | cod`
- `external_order_id text` NULL
- `order_number text` NULL (human-facing)
- `test_id uuid` NULL
- `test_phase text` NULL - `before_test | during_test | after_test`
- `status text` - `pending | confirmed | fulfilled | cancelled | returned`
- `currency char(3)`
- `subtotal_minor bigint`, `shipping_minor bigint`, `discount_minor bigint`, `total_minor bigint`
- `customer_name text` NULL
- `customer_phone text` NULL
- `customer_address_enc bytea` NULL (ciphertext)
- `landing_page_id uuid` NULL
- `post_id uuid` NULL
- `campaign_id uuid` NULL
- `tracking_session_id uuid` NULL
- `import_batch_id uuid` NULL
- `dedupe_hash char(64)` NULL
- `placed_at timestamptz`
- `imported_at timestamptz` NULL
- UNIQUE (`store_id`, `external_order_id`) where not null; UNIQUE (`store_id`, `dedupe_hash`) where not null
- INDEX (`store_id`, `test_id`, `test_phase`), (`store_id`, `placed_at`)
- Tenant base.
- Note: rows without an order ID create one Order per row; rows sharing `external_order_id` group into one Order with multiple items.

**OrderItem** - Order line.
- `order_id uuid`
- `product_id uuid` NULL
- `product_external_id text` NULL
- `product_name_snapshot text`
- `sku_snapshot text` NULL
- `quantity int` CHECK > 0
- `unit_price_minor bigint`
- `line_total_minor bigint`
- `currency char(3)`
- `metadata jsonb`
- Tenant base minus `updated_at`.

---

### Audience & Store Context

**Category** - Global taxonomy node.
- `parent_id uuid` NULL (self-reference)
- `name text`
- `slug text` UNIQUE
- `is_active boolean`
- `sort_order int`
- `Base`.

**Niche** - Curated or store-specific niche.
- `category_id uuid`
- `store_id uuid` NULL (null means global curated)
- `name text`
- `slug text`
- `is_active boolean`
- `Base`.
- Partial UNIQUE (`store_id`, `slug`) where `store_id` not null.

**AudienceProfile** - Versioned audience definition.
- `version int`
- `status text` - `draft | active | archived`
- `is_current boolean`
- `niche_ids uuid[]`
- `languages text[]`
- `notes text`
- `created_by uuid`
- UNIQUE (`store_id`, `version`); partial UNIQUE (`store_id`) where `is_current`
- Tenant base.

**AudienceSegment** - Segment under a profile.
- `audience_profile_id uuid`
- `label text`
- `locations jsonb` - array of country or region codes
- `age_min int`, `age_max int`
- `genders text[]`
- `interests text[]`
- `languages text[]`
- CHECK (`age_min <= age_max`)
- Tenant base minus `updated_at`.

**FeedbackItem** - Customer feedback entry.
- `audience_profile_id uuid` NULL
- `source text` - `manual | file`
- `stored_file_id uuid` NULL
- `text text`
- `language text` NULL
- `sentiment text` NULL - `positive | neutral | negative`
- `captured_at timestamptz`
- Tenant base minus `updated_at`.

---

### Product Evaluation

**ProductConcept** - Candidate product.
- `source_idea_id uuid` NULL
- `name text`
- `description text`
- `category_id uuid`
- `niche_id uuid` NULL
- `price_minor bigint`, `cost_minor bigint`, `currency char(3)`
- `gross_margin_bp int`
- `image_file_id uuid` NULL
- `status text` - `draft | evaluated | selected | archived`
- `version int`
- `created_by uuid`
- `deleted_at timestamptz`
- Tenant base.

**SufficiencyCheck** - Data availability result.
- `product_concept_id uuid`
- `sales_history_status text` - `available | missing | stale | insufficient`
- `audience_status text` - same enum
- `cost_price_status text` - same enum
- `competitive_data_status text` - same enum
- `overall_status text` - `sufficient | insufficient`
- `blocking_reasons jsonb`
- `checked_at timestamptz`
- Tenant base minus `updated_at`.

**Evaluation** - One scoring run.
- `product_concept_id uuid`
- `scoring_model_id uuid`
- `model_version int`
- `score numeric(7,4)` NULL (null when unavailable)
- `score_scale smallint` default 100
- `confidence text` - `high | medium | low`
- `is_reliable boolean`
- `sufficiency_check_id uuid` NULL
- `input_snapshot jsonb`
- `evaluated_at timestamptz`
- Tenant base minus `updated_at`.

**ScoreFactor** - Explainability contribution.
- `evaluation_id uuid`
- `factor_key text`
- `factor_label text`
- `direction text` - `positive | negative | neutral`
- `contribution numeric(7,4)`
- `explanation text`
- `evidence jsonb`
- Tenant base minus `updated_at`.

**ScoringModel** - Versioned scoring definition.
- `store_id uuid` NULL (null means platform default)
- `key text`
- `version int`
- `name text`
- `description text`
- `weights jsonb`
- `parameters jsonb`
- `is_active boolean`
- `effective_from timestamptz`
- UNIQUE (`key`, `version`)
- `Base` with nullable `store_id`.

---

### Recommendations

**GenerationRun** - Recommendation request metadata.
- `requested_by uuid`
- `model_version text`
- `input_snapshot jsonb`
- `requested_count int`, `returned_count int`
- `status text` - `queued | running | succeeded | failed`
- `error_message text`
- `started_at`, `finished_at timestamptz`
- Tenant base minus `updated_at`.

**ProductIdea** - AI-suggested product.
- `generation_run_id uuid`
- `name text`
- `description text`
- `category_id uuid` NULL
- `niche_id uuid` NULL
- `rationale text`
- `state text` - `new | saved | dismissed | converted`
- `dismissed_reason text` NULL
- `converted_concept_id uuid` NULL
- `model_version text`
- Tenant base.

**IdeaEvidence** - Provenance item.
- `product_idea_id uuid`
- `evidence_type text` - `verified | hypothesis`
- `claim text`
- `source_name text` NULL
- `source_url text` NULL
- `source_published_at timestamptz` NULL
- `retrieved_at timestamptz` NULL
- `confidence numeric(5,4)` NULL
- CHECK (`evidence_type = 'verified'` requires `source_url`)
- Tenant base minus `updated_at`.

---

### Assets, Campaigns & Tests

**LandingPage** - Product-test page.
- `product_concept_id uuid`
- `test_id uuid` NULL
- `slug text` UNIQUE
- `status text` - `draft | published | unpublished`
- `template_id uuid`
- `current_version_id uuid` NULL
- `published_version_id uuid` NULL
- `order_channel_id uuid` NULL
- `language text`, `currency char(3)`
- `published_url text` NULL
- `published_at timestamptz` NULL
- `deleted_at timestamptz`
- Tenant base.

**PageVersion** - Immutable page snapshot.
- `landing_page_id uuid`
- `version int`
- `content jsonb` - sections, copy, layout values
- `price_minor bigint`, `currency char(3)`
- `image_file_ids uuid[]`
- `order_channel_id uuid`
- `generated_by text` - `ai | manual`
- `model_version text` NULL
- `created_by uuid`
- UNIQUE (`landing_page_id`, `version`)
- Tenant base minus `updated_at`.

**PageTemplate** - Versioned layout.
- `key text`
- `version int`
- `name text`
- `is_active boolean`
- `schema jsonb`
- UNIQUE (`key`, `version`)
- `Base`.

**OrderChannel** - WhatsApp or COD configuration.
- `landing_page_id uuid` NULL
- `post_id uuid` NULL
- `type text` - `whatsapp | cod`
- `whatsapp_number text` NULL
- `whatsapp_message_template text` NULL
- `cod_form_schema jsonb` NULL
- `is_active boolean`
- CHECK (`type = 'whatsapp'` requires `whatsapp_number`; `cod` requires `cod_form_schema`)
- CHECK ((`landing_page_id` IS NOT NULL AND `post_id` IS NULL) OR (`landing_page_id` IS NULL AND `post_id` IS NOT NULL))
- Tenant base.

**Test** - Central product test.
- `product_concept_id uuid`
- `landing_page_id uuid` NULL
- `post_id uuid` NULL
- `name text`
- `status text` - `draft | running | paused | awaiting_verdict | completed | extended | cancelled`
- `primary_conversion text` - `whatsapp_click | cod_order | deposit_confirmed`
- `currency char(3)`
- `total_budget_minor bigint`, `daily_budget_minor bigint`, `spend_minor bigint`
- `planned_start_at`, `planned_end_at timestamptz`
- `actual_start_at`, `actual_end_at timestamptz` NULL
- `created_by uuid`
- CHECK ((`landing_page_id` IS NOT NULL AND `post_id` IS NULL) OR (`landing_page_id` IS NULL AND `post_id` IS NOT NULL) OR (`status` = 'draft'))
- Tenant base.

**TestExtension** - Extension of an inconclusive test.
- `test_id uuid`
- `previous_end_at timestamptz`, `new_end_at timestamptz`
- `added_budget_minor bigint`, `currency char(3)`
- `reason text`
- `approved_by uuid`
- Tenant base minus `updated_at`.

**Campaign** - Ad campaign.
- `test_id uuid`
- `provider text`
- `external_campaign_id text` NULL
- `name text`
- `objective text`
- `status text` - `draft | submitted | active | paused | rejected | failed | completed`
- `budget_type text` - `daily | total`
- `budget_minor bigint`, `currency char(3)`
- `start_at`, `end_at timestamptz`
- `created_by uuid`
- Tenant base.

**AdSet** - Targeting and budget group within a campaign.
- `campaign_id uuid`
- `external_adset_id text` NULL
- `name text`
- `status text` - same as Campaign
- `targeting jsonb` - locations, age range, genders, interests, languages
- `budget_type text` NULL
- `budget_minor bigint` NULL (null when campaign-level budget optimization is used)
- `currency char(3)`
- `start_at`, `end_at timestamptz`
- Tenant base.

**AdVariation** - Ad creative and copy.
- `adset_id uuid`
- `external_ad_id text` NULL
- `name text` NULL
- `copy_text text`
- `headline text` NULL
- `description text` NULL
- `creative_file_id uuid` NULL
- `primary_creative_id uuid` NULL
- `post_id uuid` NULL
- `destination_url text` NULL
- `status text` - `draft | approved | discarded | submitted | active | paused | rejected | failed`
- `rejection_reason text` NULL
- CHECK (`post_id` IS NOT NULL OR `destination_url` IS NOT NULL)
- Tenant base.

**TrackingLink** - Attribution token.
- `test_id uuid`, `campaign_id uuid`
- `adset_id uuid` NULL, `ad_variation_id uuid` NULL
- `landing_page_id uuid` NULL
- `post_id uuid` NULL
- `token text` UNIQUE
- `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term text` NULL
- `destination_url text`
- CHECK (`landing_page_id` IS NOT NULL OR `post_id` IS NOT NULL)
- Tenant base minus `updated_at`.

**PublicationAttempt** - Submission attempt.
- `campaign_id uuid` NULL
- `adset_id uuid` NULL
- `ad_variation_id uuid` NULL
- `provider text`
- `attempt_number int`
- `status text` - `pending | submitted | succeeded | failed`
- `external_id text` NULL
- `request_payload jsonb` (redacted)
- `response_payload jsonb`
- `error_code text`, `error_message text`
- `submitted_by uuid`
- `submitted_at timestamptz`
- CHECK (exactly one of campaign, ad set, or ad variation is targeted)
- Tenant base minus `updated_at`.

---

### Measurement

**TrackingSession** - Visitor session.
- `landing_page_id uuid`
- `test_id uuid` NULL
- `campaign_id uuid` NULL
- `first_utm_source`, `first_utm_medium`, `first_utm_campaign`, `first_utm_content`, `first_utm_term text` NULL
- `referrer text` NULL
- `user_agent text`
- `ip_hash char(64)` (no raw IP)
- `consent_state text` - `unknown | granted | denied`
- `started_at timestamptz`, `last_seen_at timestamptz`
- Tenant base minus `updated_at`.

**Event** - Typed behavioral event (append-only).
- `event_id uuid` UNIQUE (client-generated; idempotency)
- `tracking_session_id uuid` NULL
- `test_id uuid` NULL
- `product_id uuid` NULL
- `campaign_id uuid` NULL
- `adset_id uuid` NULL
- `ad_variation_id uuid` NULL
- `event_type text` - `page_view | product_view | cta_click | whatsapp_click | cod_form_start | cod_order_submitted | deposit_confirmed`
- `source text` - `web | server`
- `url text`, `referrer text` NULL
- `occurred_at timestamptz`, `received_at timestamptz`
- `is_bot boolean`
- `properties jsonb`
- INDEX (`store_id`, `event_type`, `occurred_at`), (`tracking_session_id`)
- Tenant base minus `updated_at`.

**Deposit** - Pre-order deposit.
- `order_id uuid`
- `test_id uuid` NULL
- `status text` - `pending | confirmed | rejected`
- `amount_minor bigint`, `currency char(3)`
- `method text` - `manual | payment_gateway`
- `evidence_file_id uuid` NULL
- `external_payment_id text` NULL
- `verified_by uuid` NULL
- `verified_at timestamptz` NULL
- Tenant base.

**Attribution** - Resolved attribution result.
- `subject_type text` - `event | order`
- `subject_id uuid`
- `test_id uuid` NULL
- `campaign_id uuid` NULL, `adset_id uuid` NULL, `ad_variation_id uuid` NULL
- `model text` - `last_touch | first_touch | direct`
- `window_seconds int`
- `is_attributed boolean`
- `confidence numeric(5,4)`
- `resolved_at timestamptz`
- UNIQUE (`subject_type`, `subject_id`)
- Tenant base minus `updated_at`.

**MetricSnapshot** - Campaign and ad metrics per sync.
- `test_id uuid`
- `provider text`
- `campaign_id uuid`
- `adset_id uuid` NULL
- `ad_variation_id uuid` NULL
- `period_start timestamptz`, `period_end timestamptz`
- `snapshot_at timestamptz`
- `currency char(3)`
- `spend_minor bigint`
- `impressions bigint`, `reach bigint`
- `frequency numeric(9,4)`
- `clicks bigint`
- `ctr numeric(9,6)`
- `cpc_minor bigint`, `cpm_minor bigint`
- `engagement bigint`
- `platform_conversions bigint`
- `cost_per_conversion_minor bigint`
- `raw jsonb`
- UNIQUE NULLS NOT DISTINCT (`campaign_id`, `adset_id`, `ad_variation_id`, `period_start`, `period_end`)
- Tenant base minus `updated_at`.

---

### Optimization

**OptimizationRuleSet** - Versioned thresholds.
- `store_id uuid` NULL
- `scope text` - `global | store | campaign`
- `campaign_id uuid` NULL
- `version int`
- `is_active boolean`
- `min_impressions int`, `min_clicks int`, `min_conversions int`
- `ctr_floor numeric(9,6)`
- `cpc_ceiling_minor bigint`
- `cost_per_conversion_ceiling_minor bigint`
- `rules jsonb`
- `created_by uuid`
- CHECK (`scope = 'campaign'` requires `campaign_id`)
- UNIQUE NULLS NOT DISTINCT (`store_id`, `scope`, `campaign_id`, `version`)
- `Base`.

**PerformanceFinding** - Flagged performance.
- `campaign_id uuid`
- `adset_id uuid` NULL
- `ad_variation_id uuid` NULL
- `rule_set_id uuid`
- `status text` - `underperforming | promising | insufficient_data`
- `metric_key text`
- `observed_value numeric`
- `threshold_value numeric`
- `reason_code text`
- `data_window_start`, `data_window_end timestamptz`
- `evaluated_at timestamptz`
- Tenant base minus `updated_at`.

**OptimizationRecommendation** - Proposed action.
- `finding_id uuid` NULL
- `campaign_id uuid`
- `adset_id uuid` NULL
- `ad_variation_id uuid` NULL
- `action text` - `pause | keep | reallocate | increase_budget | decrease_budget`
- `rationale text`
- `proposed_changes jsonb`
- `expected_impact jsonb`
- `budget_impact_minor bigint`, `currency char(3)`
- `status text` - `pending | accepted | dismissed | executed | expired`
- Tenant base.

**OptimizationAction** - Executed change.
- `recommendation_id uuid` NULL
- `campaign_id uuid`
- `adset_id uuid` NULL
- `ad_variation_id uuid` NULL
- `action_type text`
- `actor_type text` - `user | system`
- `actor_user_id uuid` NULL
- `before_state jsonb`, `after_state jsonb`
- `reason text`
- `external_reference text` NULL
- `status text` - `succeeded | failed | reverted`
- `executed_at timestamptz`, `reverted_at timestamptz` NULL
- Tenant base minus `updated_at`.

**BudgetPolicy** - Spending caps.
- `test_id uuid` NULL
- `campaign_id uuid` NULL
- `total_cap_minor bigint`, `daily_cap_minor bigint`
- `currency char(3)`
- `enforcement text` - `hard | soft`
- `is_active boolean`
- `created_by uuid`
- CHECK (at least one of `test_id` or `campaign_id`)
- Tenant base.

**Alert** - Operational notification.
- `type text` - `overspend | sync_failure | anomaly | publication_failure`
- `severity text` - `info | warning | critical`
- `title text`, `message text`
- `related_type text`, `related_id uuid`
- `status text` - `open | acknowledged | resolved`
- `acknowledged_by uuid` NULL
- `resolved_at timestamptz` NULL
- Tenant base.

---

### Decision & Investment

**DecisionRuleSet** - Versioned verdict thresholds.
- `store_id uuid` NULL
- `category_id uuid` NULL
- `version int`
- `is_active boolean`
- `min_spend_minor bigint`
- `min_clicks int`, `min_conversions int`, `min_confirmed_deposits int`
- `min_conversion_rate numeric(9,6)`
- `max_cost_per_conversion_minor bigint`
- `rules jsonb`
- `created_by uuid`
- UNIQUE NULLS NOT DISTINCT (`store_id`, `category_id`, `version`)
- `Base`.

**TestResultSnapshot** - Frozen verdict inputs.
- `test_id uuid`
- `period_start`, `period_end timestamptz`
- `currency char(3)`
- `spend_minor bigint`
- `impressions bigint`, `clicks bigint`
- `tracked_conversions bigint`, `confirmed_deposits bigint`
- `conversion_rate numeric(9,6)`
- `cost_per_conversion_minor bigint`
- `data_completeness numeric(5,4)`
- `source_metric_snapshot_ids uuid[]`
- `captured_at timestamptz`
- Tenant base minus `updated_at`.

**Verdict** - Test outcome.
- `test_id uuid`
- `result_snapshot_id uuid`
- `decision_rule_set_id uuid`
- `outcome text` - `go | no_go | extend_test`
- `is_conclusive boolean`
- `primary_reason text`
- `limitations jsonb`
- `rule_trace jsonb`
- Tenant base minus `updated_at`.

**InvestmentProfile** - Versioned investment inputs.
- `test_id uuid`
- `version int`
- `unit_cost_minor bigint`
- `selling_price_minor bigint`
- `fulfillment_cost_minor bigint`
- `payment_fee_bp int`
- `available_budget_minor bigint`
- `target_margin_bp int`
- `supplier_moq int`
- `lead_time_days int`
- `currency char(3)`
- `is_current boolean`
- `created_by uuid`
- UNIQUE (`test_id`, `version`)
- Tenant base.

**InvestmentRecommendation** - Versioned computed output root.
- `test_id uuid`
- `investment_profile_id uuid`
- `version int`
- `summary text`
- `assumptions_snapshot jsonb`
- `is_current boolean`
- `created_by uuid`
- UNIQUE (`test_id`, `version`)
- Tenant base.

**DemandEstimate** - Demand projection.
- `investment_recommendation_id uuid`
- `low_units int`, `base_units int`, `high_units int`
- `assumptions jsonb`
- `confidence text` - `high | medium | low`
- Tenant base minus `updated_at`.

**UnitEconomics** - Per-unit economics.
- `investment_recommendation_id uuid`
- `contribution_margin_minor bigint`
- `break_even_units numeric(12,2)`
- `cac_minor bigint`
- `formulas jsonb`
- `is_negative_margin boolean`
- Tenant base minus `updated_at`.

**QuantityScenario** - Order quantity option.
- `investment_recommendation_id uuid`
- `label text` - `conservative | base | aggressive`
- `quantity int`
- `inventory_cost_minor bigint`
- `expected_units_sold_low int`, `expected_units_sold_high int`
- `revenue_low_minor bigint`, `revenue_high_minor bigint`
- `profit_low_minor bigint`, `profit_high_minor bigint`
- `sell_through_low numeric(5,4)`, `sell_through_high numeric(5,4)`
- `overstock_risk text` - `low | medium | high`
- `stockout_risk text` - `low | medium | high`
- `is_feasible boolean`
- `infeasibility_reason text` NULL
- Tenant base minus `updated_at`.

---

### Reference Data

**Country** - `code char(2) PK`, `name text`, `is_active boolean`.
**Currency** - `code char(3) PK`, `name text`, `minor_unit smallint`, `is_active boolean`.
**Language** - `code text PK`, `name text`, `direction text` (`ltr | rtl`), `is_active boolean`.
**AdPlatform** - `code text PK`, `name text`, `is_active boolean`.
**EventType** - `code text PK`, `description text`, `is_active boolean`.

**Post** - Social/native post attached to a test.
- `test_id uuid`
- `product_concept_id uuid` NULL
- `product_id uuid` NULL
- `name text`
- `slug text` UNIQUE NULL
- `text_content jsonb` - caption, body, hooks, hashtags, mentions, schema_version
- `cta_text text` NULL
- `cta_type text` NULL
- `order_channel_id uuid` NULL
- `status text` - `draft | published | unpublished | archived`
- `platform_context jsonb`
- `published_url text` NULL
- `published_at timestamptz` NULL
- `created_by uuid`
- `deleted_at timestamptz` NULL
- Tenant base.

**PostCreative** - Ordered creatives for a post.
- `post_id uuid`
- `creative_id uuid`
- `position int`
- `is_primary boolean` default false
- `overlay_text jsonb` NULL
- UNIQUE (`post_id`, `creative_id`)
- UNIQUE (`post_id`, `position`)
- Tenant base minus `updated_at`.

**Creative** - Reusable media asset.
- `source text` - `uploaded | ai_generated`
- `type text` - `image | video | gif`
- `stored_file_id uuid` NULL
- `external_url text` NULL
- `content_generation_job_id uuid` NULL
- `width int` NULL
- `height int` NULL
- `duration_ms int` NULL
- `aspect_ratio text` NULL
- `alt_text text` NULL
- `prompt text` NULL
- `model_version text` NULL
- `status text` - `draft | approved | rejected | archived`
- `approval_state text` - `pending | approved | rejected`
- `metadata jsonb`
- `deleted_at timestamptz` NULL
- CHECK ((`stored_file_id` IS NOT NULL) OR (`external_url` IS NOT NULL))
- Tenant base.

**CreativeVariant** - Media variants for tracking different sizes/aspect ratios.
- `creative_id uuid`
- `stored_file_id uuid` NULL
- `external_url text` NULL
- `width int` NULL
- `height int` NULL
- `aspect_ratio text` NULL
- `format text` NULL
- `bitrate_kbps int` NULL
- `duration_ms int` NULL
- `is_primary boolean` default false
- `metadata jsonb`
- CHECK ((`stored_file_id` IS NOT NULL) OR (`external_url` IS NOT NULL))
- Tenant base minus `updated_at`.

---

### Scalability Notes

1. **Future multi-store.** Today: `Store.owner_user_id` plus `User.role`. Later, add `Membership(user_id, store_id, role)` and migrate the role; all tenant tables already carry `store_id`, so no data-model rewrite is needed.
2. **Partitioning ready.** `Event`, `Order`, and `MetricSnapshot` are the high-volume tables; partition by month on `occurred_at`, `placed_at`, and `period_start` when volume grows. MVP keeps `id uuid` as the primary key; partitioning later requires the partition key in the PK, so the exact `ALTER` plan must be recorded before it is applied.
3. **Row-level security.** Enforce RLS on `store_id` for every tenant table, including child tables (`OrderItem`, `ScoreFactor`, `ImportRow`). Rows with `store_id IS NULL` are platform-global: readable by authenticated roles, writable only by the maintenance/owner role.
4. **Snapshot versus derived.** `OrderItem` line totals, `Evaluation.score`, `Verdict.rule_trace`, and `MetricSnapshot` values are stored snapshots for auditability. Rates such as `ctr` are stored on snapshots because platform data is not recomputable.
5. **JSONB discipline.** `targeting`, `rules`, `assumptions`, and `content` are versioned payloads; add a `schema_version` key inside each so future structure changes are explicit.
6. **PII.** `Order.customer_name`, `customer_phone`, and `customer_address_enc` (ciphertext) require encryption at rest and access controls; feedback text requires the same. Events and audit logs store `ip_hash`, never raw IP.

## OOP Classes, Interfaces, Value Objects & Services

### Base Abstractions
| Class/Interface | Type | Attributes/Members | Methods/Operations | Purpose |
| :-- | :-- | :-- | :-- | :-- |
| `BaseEntity` | Abstract Class | `-id: Guid`, `-createdAt: DateTimeOffset`, `-updatedAt: DateTimeOffset?` | `+getId(): Guid`, `+getCreatedAt(): DateTimeOffset`, `+getUpdatedAt(): DateTimeOffset?`, `+setUpdatedAt(d: DateTimeOffset): void` | Base for mutable domain objects |
| `TenantEntity` | Abstract Class extends `BaseEntity` | `-storeId: Guid` | `+getStoreId(): Guid` | Base for tenant-scoped entities |
| `AppendOnlyEntity` | Abstract Class | `-id: Guid`, `-createdAt: DateTimeOffset` | `+getId(): Guid`, `+getCreatedAt(): DateTimeOffset` | Base for immutable audit/event records |

### Value Objects
| Class/Interface | Type | Attributes/Members | Methods/Operations | Purpose |
| :-- | :-- | :-- | :-- | :-- |
| `Money` | Value Object (immutable) | `-amountMinor: long`, `-currency: string` | `+getAmountMinor(): long`, `+getCurrency(): string`, `+add(other: Money): Money`, `+subtract(other: Money): Money`, `+multiply(factor: decimal): Money`, `+validate(): bool` | Money in minor units |
| `DateRange` | Value Object (immutable) | `-start: DateTimeOffset`, `-end: DateTimeOffset` | `+getStart(): DateTimeOffset`, `+getEnd(): DateTimeOffset`, `+contains(date: DateTimeOffset): bool`, `+validate(): bool` | Time window validation |
| `AuditMeta` | Value Object (immutable) | `-actorUserId: Guid?`, `-actorType: ActorType`, `-correlationId: Guid?`, `-ipHash: string?` | `+getActorUserId(): Guid?`, `+getActorType(): ActorType`, `+getCorrelationId(): Guid?`, `+getIpHash(): string?` | Audit context |

### Repositories
| Class/Interface | Type | Attributes/Members | Methods/Operations | Purpose |
| :-- | :-- | :-- | :-- | :-- |
| `IRepository<T>` | Interface | - | `+getById(id: Guid): Task<T?>`, `+list(filters: object): Task<List<T>>`, `+add(entity: T): Task<T>`, `+update(entity: T): Task<T>`, `+remove(entity: T): Task<void>` | Generic repository |
| `IStoreRepository` | Interface extends `IRepository<Store>` | - | `+getByOwner(userId: Guid): Task<Store?>`, `+getBySlug(slug: string): Task<Store?>`, `+create(store: Store): Task<Store>`, `+update(store: Store): Task<Store>`, `+softDelete(id: Guid): Task<void>` | Store queries |
| `IUserRepository` | Interface extends `IRepository<User>` | - | `+getByEmail(email: string): Task<User?>`, `+existsByEmail(email: string): Task<bool>` | User queries |

### Domain Services / Use Cases
| Class/Interface | Type | Attributes/Members | Methods/Operations | Purpose |
| :-- | :-- | :-- | :-- | :-- |
| `IAuthorizationService` | Interface | - | `+checkPermission(storeId: Guid, userId: Guid, action: string): Task<PermissionResult>` | RBAC |
| `IAuditService` | Interface | - | `+log(action: string, targetType: string, targetId: Guid, before: object?, after: object?, meta: AuditMeta): Task<AuditLog>` | Audit logging |
| `IImportService` | Interface | - | `+uploadCsv(storeId: Guid, file: Stream): Task<StoredFile>`, `+createBatch(storeId: Guid, fileId: Guid, strict: bool): Task<ImportBatch>`, `+suggestMapping(batchId: Guid): Task<MappingSuggestion>`, `+applyMapping(batchId: Guid, mappingId: Guid): Task<void>`, `+validate(batchId: Guid): Task<ValidationResult>`, `+preview(batchId: Guid, limit: int, offset: int): Task<PreviewResult>`, `+commit(batchId: Guid): Task<ImportSummary>` | Imports |
| `IAudienceService` | Interface | - | `+getCurrentProfile(storeId: Guid): Task<AudienceProfile>`, `+upsertProfile(storeId: Guid, dto: object): Task<AudienceProfile>`, `+submitFeedback(storeId: Guid, dto: object): Task<FeedbackItem>` | Audience |
| `IEvaluationService` | Interface | - | `+runSufficiencyCheck(conceptId: Guid): Task<SufficiencyCheck>`, `+evaluate(conceptId: Guid, modelId: Guid?): Task<Evaluation>`, `+batchEvaluate(storeId: Guid, conceptIds: List<Guid>): Task<List<Evaluation>>`, `+compare(conceptIds: List<Guid>): Task<ComparisonResult>` | Evaluation |
| `IRecommendationService` | Interface | - | `+generate(storeId: Guid, requestedBy: Guid, count: int): Task<GenerationRun>`, `+getIdeas(storeId: Guid, filters: object): Task<List<ProductIdea>>`, `+save(ideaId: Guid): Task<ProductIdea>`, `+dismiss(ideaId: Guid, reason: string?): Task<ProductIdea>`, `+convertToConcept(ideaId: Guid): Task<ProductConcept>` | Recommendations |
| `ILandingPageService` | Interface | - | `+create(storeId: Guid, conceptId: Guid, testId: Guid?, templateId: Guid): Task<LandingPage>`, `+updateDraft(pageId: Guid, updates: object): Task<PageVersion>`, `+preview(pageId: Guid): Task<PreviewResult>`, `+publish(pageId: Guid): Task<LandingPage>`, `+unpublish(pageId: Guid): Task<LandingPage>` | Landing pages |
| `IPostService` | Interface | - | `+createPost(storeId: Guid, dto: object): Task<Post>`, `+addCreatives(postId: Guid, creativeIds: List<Guid>, positions: List<int>): Task<List<PostCreative>>`, `+publish(postId: Guid): Task<Post>` | Posts |
| `ICampaignService` | Interface | - | `+authorizeAccount(storeId: Guid, provider: string): Task<AuthUrl>`, `+createCampaign(storeId: Guid, dto: object): Task<Campaign>`, `+createAdSet(campaignId: Guid, dto: object): Task<AdSet>`, `+generateVariations(dto: object): Task<List<AdVariation>>`, `+approveVariation(id: Guid): Task<AdVariation>`, `+publish(campaignId: Guid, approvedBy: Guid): Task<PublicationAttempt>` | Campaigns |
| `IContentService` | Interface | - | `+listProviders(storeId: Guid): Task<List<ContentProvider>>`, `+createJob(storeId: Guid, dto: object): Task<ContentGenerationJob>`, `+getJobStatus(jobId: Guid): Task<ContentGenerationJob>`, `+uploadCreative(storeId: Guid, file: Stream, altText: string?): Task<Creative>` | Content |
| `ITrackingService` | Interface | - | `+createSession(storeId: Guid, dto: object): Task<TrackingSession>`, `+recordEvent(storeId: Guid, dto: object): Task<Event>`, `+trackWhatsAppClick(sessionId: Guid, dto: object): Task<RedirectResult>`, `+submitCodOrder(storeId: Guid, dto: object): Task<Order>`, `+confirmDeposit(orderId: Guid, dto: object): Task<Deposit>`, `+resolveAttribution(string,Guid): Task<Attribution>`, `+getMetrics(storeId: Guid, filters: object): Task<MetricsResult>` | Tracking |
| `IOptimizationService` | Interface | - | `+syncMetrics(storeId: Guid, campaignIds: List<Guid>): Task<List<MetricSnapshot>>`, `+evaluatePerformance(campaignId: Guid): Task<List<PerformanceFinding>>`, `+getRecommendations(campaignId: Guid): Task<List<OptimizationRecommendation>>`, `+acceptRecommendation(id: Guid, actorId: Guid): Task<OptimizationRecommendation>`, `+dismissRecommendation(id: Guid, actorId: Guid): Task<OptimizationRecommendation>` | Optimization |
| `IVerdictService` | Interface | - | `+computeSnapshot(testId: Guid, period: DateRange): Task<TestResultSnapshot>`, `+evaluateVerdict(testId: Guid): Task<Verdict>`, `+extendTest(testId: Guid, dto: object): Task<TestExtension>` | Verdicts |
| `IInvestmentService` | Interface | - | `+upsertProfile(testId: Guid, dto: object): Task<InvestmentProfile>`, `+computeRecommendation(testId: Guid, profileId: Guid): Task<InvestmentRecommendation>`, `+getRecommendation(testId: Guid): Task<InvestmentDetail>`, `+recalculate(testId: Guid, profileId: Guid, overrides: object): Task<InvestmentRecommendation>` | Investment |

### Strategies & External Clients
| Class/Interface | Type | Attributes/Members | Methods/Operations | Purpose |
| :-- | :-- | :-- | :-- | :-- |
| `IScoringStrategy` | Interface | - | `+score(ProductConcept,object,ScoringModel): Task<EvaluationResult>` | Scoring strategy |
| `IAttributionStrategy` | Interface | - | `+resolve(string,Guid,object): Task<Attribution>` | Attribution strategy |
| `IVerdictEvaluator` | Interface | - | `+evaluate(TestResultSnapshot,DecisionRuleSet): Task<VerdictResult>` | Verdict strategy |
| `IOptimizationRuleEvaluator` | Interface | - | `+evaluate(FindingContext,OptimizationRuleSet): Task<FindingResult>` | Optimization strategy |
| `IDemandEstimator` | Interface | - | `+estimate(TestResultSnapshot,InvestmentProfile): Task<DemandEstimate>` | Demand strategy |
| `IInvestmentCalculator` | Interface | - | `+calculateEconomics(InvestmentProfile,DemandEstimate): Task<UnitEconomics>`, `+generateScenarios(InvestmentProfile,DemandEstimate,UnitEconomics): Task<List<QuantityScenario>>` | Investment calc |
| `IAdPlatformClient` | Interface | - | `+publishCampaign(object): Task<PublishResult>`, `+publishAdSet(object): Task<PublishResult>`, `+publishAd(object): Task<PublishResult>`, `+getMetrics(object): Task<MetricsResult>`, `+refreshToken(object): Task<CredsResult>` | Platform client |
| `IJobProcessor<T>` | Interface | - | `+process(AsyncJob): Task<JobResult>` | Job processor |

### Infrastructure & Cross-Cutting
| Class/Interface | Type | Attributes/Members | Methods/Operations | Purpose |
| :-- | :-- | :-- | :-- | :-- |
| `IJobQueue` | Interface | - | `+enqueue(JobType,object,string?,Guid?): Task<AsyncJob>` | Job queue |
| `IFileStorage` | Interface | - | `+upload(Stream,string,string): Task<StoredFile>`, `+getDownloadUrl(string): Task<string>`, `+delete(string): Task<void>` | Storage |
| `IUnitOfWork` | Interface | - | `+saveChangesAsync(): Task<int>`, `+beginTransaction(): Task<ITransaction>`, `+commit(): Task<void>`, `+rollback(): Task<void>` | UoW |
| `ITenantContext` | Interface | `+storeId: Guid`, `+userId: Guid`, `+role: UserRole` | - | Tenant context |
| `IRowLevelSecurity` | Interface | - | `+applyFilter<T>(query: IQueryable<T>, storeId: Guid): IQueryable<T>` | RLS |
| `IdempotencyService` | Service Class | `-store: IIdempotencyStore` | `+check(key: string): Task<IdempotentResult>`, `+store(key: string, response: object, ttl: TimeSpan): Task<void>` | Idempotency |
| `ValidationService` | Service Class | - | `+validateModel<T>(model: T): ValidationResult` | Validation |
| `CorrelationService` | Service Class | - | `+getCorrelationId(): Guid`, `+setCorrelationId(id: Guid): void` | Correlation |
| `RateLimitService` | Service Class | - | `+checkLimit(key: string, policy: RateLimitPolicy): Task<RateLimitResult>` | Rate limiting |

## OOP Class Diagram

`mermaid
classDiagram
    class BaseEntity {
        <<abstract>>
        -Guid id
        -DateTimeOffset createdAt
        -DateTimeOffset? updatedAt
        +getId() Guid
        +getCreatedAt() DateTimeOffset
        +getUpdatedAt() DateTimeOffset?
        +setUpdatedAt(d: DateTimeOffset) void
    }
    class TenantEntity {
        <<abstract>>
        -Guid storeId
        +getStoreId() Guid
    }
    class AppendOnlyEntity {
        <<abstract>>
        -Guid id
        -DateTimeOffset createdAt
        +getId() Guid
        +getCreatedAt() DateTimeOffset
    }

    class Money {
        <<value object>>
        -long amountMinor
        -string currency
        +getAmountMinor() long
        +getCurrency() string
        +add(other: Money) Money
        +subtract(other: Money) Money
        +multiply(factor: decimal) Money
        +validate() bool
    }
    class DateRange {
        <<value object>>
        -DateTimeOffset start
        -DateTimeOffset end
        +getStart() DateTimeOffset
        +getEnd() DateTimeOffset
        +contains(date: DateTimeOffset) bool
        +validate() bool
    }
    class AuditMeta {
        <<value object>>
        -Guid? actorUserId
        -ActorType actorType
        -Guid? correlationId
        -string? ipHash
        +getActorUserId() Guid?
        +getActorType() ActorType
        +getCorrelationId() Guid?
        +getIpHash() string?
    }

    class IRepository~T~ {
        <<interface>>
        +getById(id: Guid) Task~T?~
        +list(filters: object) Task~List~T~~
        +add(entity: T) Task~T~
        +update(entity: T) Task~T~
        +remove(entity: T) Task~void~
    }
    class IStoreRepository {
        <<interface>>
        +getByOwner(userId: Guid) Task~Store?~
        +getBySlug(slug: string) Task~Store?~
        +create(store: Store) Task~Store~
        +update(store: Store) Task~Store~
        +softDelete(id: Guid) Task~void~
    }
    class IUserRepository {
        <<interface>>
        +getByEmail(email: string) Task~User?~
        +existsByEmail(email: string) Task~bool~
        +getByAuthSubject(provider: string, subject: string) Task~User?~
    }

    class IAuthorizationService {
        <<interface>>
        +checkPermission(storeId: Guid, userId: Guid, action: string) Task~PermissionResult~
    }
    class IAuditService {
        <<interface>>
        +log(action: string, targetType: string, targetId: Guid, before: object?, after: object?, meta: AuditMeta) Task~AuditLog~
    }
    class IImportService {
        <<interface>>
        +uploadCsv(storeId: Guid, file: Stream) Task~StoredFile~
        +createBatch(storeId: Guid, fileId: Guid, strict: bool) Task~ImportBatch~
        +suggestMapping(batchId: Guid) Task~MappingSuggestion~
        +applyMapping(batchId: Guid, mappingId: Guid) Task~void~
        +validate(batchId: Guid) Task~ValidationResult~
        +preview(batchId: Guid, limit: int, offset: int) Task~PreviewResult~
        +commit(batchId: Guid) Task~ImportSummary~
        +getImportHistory(storeId: Guid, filters: object) Task~List~ImportBatch~~
        +downloadErrorReport(batchId: Guid) Task~Stream~
    }
    class IAudienceService {
        <<interface>>
        +getCurrentProfile(storeId: Guid) Task~AudienceProfile~
        +getProfileHistory(storeId: Guid) Task~List~AudienceProfile~~
        +upsertProfile(storeId: Guid, dto: object) Task~AudienceProfile~
        +upsertSegment(profileId: Guid, dto: object) Task~AudienceSegment~
        +submitFeedback(storeId: Guid, dto: object) Task~FeedbackItem~
        +uploadFeedbackFile(storeId: Guid, file: Stream) Task~StoredFile~
    }
    class IEvaluationService {
        <<interface>>
        +runSufficiencyCheck(conceptId: Guid) Task~SufficiencyCheck~
        +evaluate(conceptId: Guid, modelId: Guid?) Task~Evaluation~
        +batchEvaluate(storeId: Guid, conceptIds: List~Guid~) Task~List~Evaluation~~
        +compare(conceptIds: List~Guid~) Task~ComparisonResult~
        +getEvaluationDetails(evaluationId: Guid) Task~EvaluationDetail~
    }
    class IRecommendationService {
        <<interface>>
        +generate(storeId: Guid, requestedBy: Guid, count: int) Task~GenerationRun~
        +getIdeas(storeId: Guid, filters: object) Task~List~ProductIdea~~
        +getIdeaDetails(ideaId: Guid) Task~ProductIdeaDetail~
        +save(ideaId: Guid) Task~ProductIdea~
        +dismiss(ideaId: Guid, reason: string?) Task~ProductIdea~
        +convertToConcept(ideaId: Guid) Task~ProductConcept~
    }
    class ILandingPageService {
        <<interface>>
        +create(storeId: Guid, conceptId: Guid, testId: Guid?, templateId: Guid) Task~LandingPage~
        +getDraft(pageId: Guid) Task~LandingPageDetail~
        +generateCopy(pageId: Guid) Task~CopySuggestion~
        +updateDraft(pageId: Guid, updates: object) Task~PageVersion~
        +preview(pageId: Guid, versionId: Guid?) Task~PreviewResult~
        +configureOrderChannel(pageId: Guid, dto: object) Task~OrderChannel~
        +publish(pageId: Guid) Task~LandingPage~
        +unpublish(pageId: Guid) Task~LandingPage~
    }
    class IPostService {
        <<interface>>
        +createPost(storeId: Guid, dto: object) Task~Post~
        +addCreatives(postId: Guid, creativeIds: List~Guid~, positions: List~int~) Task~List~PostCreative~~
        +update(postId: Guid, updates: object) Task~Post~
        +publish(postId: Guid) Task~Post~
    }
    class ICampaignService {
        <<interface>>
        +authorizeAccount(storeId: Guid, provider: string) Task~AuthUrl~
        +completeAccountAuth(storeId: Guid, provider: string, code: string, state: string) Task~AdAccountConnection~
        +createCampaign(storeId: Guid, dto: object) Task~Campaign~
        +createAdSet(campaignId: Guid, dto: object) Task~AdSet~
        +generateVariations(dto: object) Task~List~AdVariation~~
        +updateAdVariation(id: Guid, updates: object) Task~AdVariation~
        +approveVariation(id: Guid) Task~AdVariation~
        +discardVariation(id: Guid) Task~AdVariation~
        +validate(campaignId: Guid) Task~ValidationResult~
        +generateTrackingLink(dto: object) Task~TrackingLink~
        +publish(campaignId: Guid, approvedBy: Guid) Task~PublicationAttempt~
    }
    class IContentService {
        <<interface>>
        +listProviders(storeId: Guid) Task~List~ContentProvider~~
        +createJob(storeId: Guid, dto: object) Task~ContentGenerationJob~
        +getJobStatus(jobId: Guid) Task~ContentGenerationJobDetail~
        +uploadCreative(storeId: Guid, file: Stream, altText: string?) Task~Creative~
        +createCreativeVariants(creativeId: Guid, variants: List~object~) Task~List~CreativeVariant~~
    }
    class ITrackingService {
        <<interface>>
        +createSession(storeId: Guid, dto: object) Task~TrackingSession~
        +recordEvent(storeId: Guid, dto: object) Task~Event~
        +trackWhatsAppClick(sessionId: Guid, dto: object) Task~RedirectResult~
        +submitCodOrder(storeId: Guid, dto: object) Task~Order~
        +confirmDeposit(orderId: Guid, dto: object) Task~Deposit~
        +resolveAttribution(subjectType: string, subjectId: Guid) Task~Attribution~
        +getMetrics(storeId: Guid, filters: object) Task~MetricsResult~
    }
    class IOptimizationService {
        <<interface>>
        +syncMetrics(storeId: Guid, campaignIds: List~Guid~) Task~List~MetricSnapshot~~
        +getCampaignMetrics(campaignId: Guid, period: DateRange) Task~CampaignMetrics~
        +upsertRuleSet(storeId: Guid, dto: object) Task~OptimizationRuleSet~
        +evaluatePerformance(campaignId: Guid) Task~List~PerformanceFinding~~
        +getRecommendations(campaignId: Guid, status: string?) Task~List~OptimizationRecommendation~~
        +acceptRecommendation(id: Guid, actorId: Guid) Task~OptimizationRecommendation~
        +dismissRecommendation(id: Guid, actorId: Guid) Task~OptimizationRecommendation~
        +upsertBudgetPolicy(storeId: Guid, dto: object) Task~BudgetPolicy~
        +getAlerts(storeId: Guid, filters: object) Task~List~Alert~~
        +acknowledgeAlert(alertId: Guid, actorId: Guid) Task~Alert~
        +resolveAlert(alertId: Guid, actorId: Guid) Task~Alert~
    }
    class IVerdictService {
        <<interface>>
        +computeSnapshot(testId: Guid, period: DateRange) Task~TestResultSnapshot~
        +upsertDecisionRuleSet(storeId: Guid, dto: object) Task~DecisionRuleSet~
        +evaluateVerdict(testId: Guid) Task~Verdict~
        +getVerdict(testId: Guid) Task~VerdictDetail~
        +extendTest(testId: Guid, dto: object) Task~TestExtension~
    }
    class IInvestmentService {
        <<interface>>
        +upsertProfile(testId: Guid, dto: object) Task~InvestmentProfile~
        +computeRecommendation(testId: Guid, profileId: Guid) Task~InvestmentRecommendation~
        +getRecommendation(testId: Guid) Task~InvestmentDetail~
        +recalculate(testId: Guid, profileId: Guid, overrides: object) Task~InvestmentRecommendation~
        +getHistory(testId: Guid) Task~List~InvestmentRecommendation~~
    }

    class IScoringStrategy {
        <<interface>>
        +score(concept: ProductConcept, inputs: object, model: ScoringModel) Task~EvaluationResult~
    }
    class IAttributionStrategy {
        <<interface>>
        +resolve(subjectType: string, subjectId: Guid, context: object) Task~Attribution~
    }
    class IVerdictEvaluator {
        <<interface>>
        +evaluate(snapshot: TestResultSnapshot, ruleSet: DecisionRuleSet) Task~VerdictResult~
    }
    class IOptimizationRuleEvaluator {
        <<interface>>
        +evaluate(context: FindingContext, ruleSet: OptimizationRuleSet) Task~FindingResult~
    }
    class IDemandEstimator {
        <<interface>>
        +estimate(snapshot: TestResultSnapshot, profile: InvestmentProfile) Task~DemandEstimate~
    }
    class IInvestmentCalculator {
        <<interface>>
        +calculateEconomics(profile: InvestmentProfile, demand: DemandEstimate) Task~UnitEconomics~
        +generateScenarios(profile: InvestmentProfile, demand: DemandEstimate, economics: UnitEconomics) Task~List~QuantityScenario~~
    }
    class IAdPlatformClient {
        <<interface>>
        +publishCampaign(req: object) Task~PublishResult~
        +publishAdSet(req: object) Task~PublishResult~
        +publishAd(req: object) Task~PublishResult~
        +getMetrics(req: object) Task~MetricsResult~
        +refreshToken(creds: object) Task~CredsResult~
    }
    class IJobProcessor~T~ {
        <<interface>>
        +process(job: AsyncJob) Task~JobResult~
    }

    class IJobQueue {
        <<interface>>
        +enqueue(jobType: JobType, payload: object, idempotencyKey: string?, correlationId: Guid?) Task~AsyncJob~
    }
    class IFileStorage {
        <<interface>>
        +upload(stream: Stream, filename: string, contentType: string) Task~StoredFile~
        +getDownloadUrl(key: string) Task~string~
        +delete(key: string) Task~void~
    }
    class IUnitOfWork {
        <<interface>>
        +saveChangesAsync() Task~int~
        +beginTransaction() Task~ITransaction~
        +commit() Task~void~
        +rollback() Task~void~
    }
    class ITenantContext {
        <<interface>>
        +Guid storeId
        +Guid userId
        +UserRole role
    }
    class IRowLevelSecurity {
        <<interface>>
        +applyFilter~T~(query: IQueryable~T~, storeId: Guid) IQueryable~T~
    }

    class IdempotencyService {
        <<service>>
        -IIdempotencyStore store
        +check(key: string) Task~IdempotentResult~
        +store(key: string, response: object, ttl: TimeSpan) Task~void~
    }
    class ValidationService {
        <<service>>
        +validateModel~T~(model: T) ValidationResult
    }
    class CorrelationService {
        <<service>>
        +getCorrelationId() Guid
        +setCorrelationId(id: Guid) void
    }
    class RateLimitService {
        <<service>>
        +checkLimit(key: string, policy: RateLimitPolicy) Task~RateLimitResult~
    }

    BaseEntity <|-- TenantEntity
    AppendOnlyEntity <|-- AuditLog
    IRepository~T~ <|-- IStoreRepository
    IRepository~T~ <|-- IUserRepository

    IImportService ..> IFileStorage
    IImportService ..> IJobQueue
    ICampaignService ..> IAdPlatformClient
    ITrackingService ..> IAttributionStrategy
    IOptimizationService ..> IOptimizationRuleEvaluator
    IOptimizationService ..> IJobQueue
    IVerdictService ..> IVerdictEvaluator
    IInvestmentService ..> IDemandEstimator
    IInvestmentService ..> IInvestmentCalculator
    IEvaluationService ..> IScoringStrategy
    IAuthorizationService ..> ITenantContext
    IJobQueue ..> IJobProcessor~T~
`




## ERD Diagram

```mermaid
erDiagram
    STORE {
        uuid id PK
        uuid owner_user_id FK
        text name
        text slug UK
        text status
        char default_currency
        text default_language
        text timezone
        char country_code
        text onboarding_status
        jsonb settings
        timestamptz created_at
        timestamptz updated_at
        timestamptz deleted_at
    }

    USER {
        uuid id PK
        citext email UK
        text password_hash
        text full_name
        text phone
        text locale
        text timezone
        text role
        text status
        timestamptz email_verified_at
        timestamptz last_login_at
        text auth_provider
        text auth_subject
        timestamptz created_at
        timestamptz updated_at
        timestamptz deleted_at
    }

    AUDIT_LOG {
        uuid id PK
        uuid store_id FK
        uuid actor_user_id FK
        text actor_type
        text action
        text target_type
        uuid target_id
        jsonb before
        jsonb after
        jsonb metadata
        char(64) ip_hash
        text user_agent
        uuid correlation_id
        timestamptz created_at
    }

    ASYNC_JOB {
        uuid id PK
        uuid store_id FK
        text job_type
        text state
        text idempotency_key UK
        jsonb payload
        jsonb result
        int progress_current
        int progress_total
        int attempt_count
        int max_attempts
        text error_code
        text error_message
        uuid correlation_id
        timestamptz scheduled_at
        timestamptz started_at
        timestamptz finished_at
        timestamptz created_at
        timestamptz updated_at
    }

    STORE_CONNECTION {
        uuid id PK
        uuid store_id FK
        text provider
        text external_store_id
        text status
        text[] scopes
        text access_token_encrypted
        text refresh_token_encrypted
        timestamptz token_expires_at
        timestamptz last_synced_at
        jsonb metadata
        timestamptz created_at
        timestamptz updated_at
    }

    AD_ACCOUNT_CONNECTION {
        uuid id PK
        uuid store_id FK
        text provider
        text external_account_id
        text account_name
        text status
        text[] scopes
        text access_token_encrypted
        text refresh_token_encrypted
        timestamptz token_expires_at
        timestamptz last_synced_at
        jsonb metadata
        timestamptz created_at
        timestamptz updated_at
    }

    CONTENT_PROVIDER {
        uuid id PK
        uuid store_id FK
        text code
        text name
        text[] media_types
        text auth_config_encrypted
        jsonb rate_limits
        jsonb pricing
        jsonb capabilities
        boolean enabled
        boolean is_default
        timestamptz created_at
        timestamptz updated_at
    }

    CONTENT_GENERATION_JOB {
        uuid id PK
        uuid store_id FK
        uuid content_provider_id FK
        text type
        text prompt
        text negative_prompt
        jsonb params
        text status
        uuid requested_by
        uuid[] result_creative_ids
        bigint cost_minor
        char currency
        text error_code
        text error_message
        uuid async_job_id
        timestamptz started_at
        timestamptz finished_at
        timestamptz created_at
    }

    STORED_FILE {
        uuid id PK
        uuid store_id FK
        text purpose
        text original_filename
        text mime_type
        bigint size_bytes
        char checksum_sha256
        text storage_provider
        text storage_key
        text status
        uuid uploaded_by_user_id
        jsonb metadata
        timestamptz created_at
        timestamptz deleted_at
    }

    IMPORT_BATCH {
        uuid id PK
        uuid store_id FK
        text source_type
        uuid stored_file_id FK
        uuid store_connection_id FK
        uuid column_mapping_id FK
        text status
        boolean strict_mode
        date date_range_start
        date date_range_end
        int total_rows
        int valid_rows
        int invalid_rows
        int duplicate_rows
        int imported_rows
        int skipped_rows
        uuid error_report_file_id FK
        timestamptz started_at
        timestamptz completed_at
        uuid created_by
        timestamptz created_at
        timestamptz updated_at
    }

    COLUMN_MAPPING {
        uuid id PK
        uuid store_id FK
        text name
        text source_type
        jsonb mapping
        boolean is_default
        uuid created_by
        timestamptz created_at
        timestamptz updated_at
    }

    IMPORT_ROW {
        uuid id PK
        uuid store_id FK
        uuid import_batch_id FK
        int row_number
        jsonb raw_data
        jsonb normalized_data
        text status
        int issue_count
        uuid created_order_id
        timestamptz created_at
    }

    IMPORT_ISSUE {
        uuid id PK
        uuid store_id FK
        uuid import_batch_id FK
        uuid import_row_id FK
        int row_number
        text field_name
        text issue_code
        text severity
        text message
        text raw_value
        timestamptz created_at
    }

    CATEGORY {
        uuid id PK
        uuid parent_id FK
        text name
        text slug UK
        boolean is_active
        int sort_order
        timestamptz created_at
        timestamptz updated_at
    }

    NICHE {
        uuid id PK
        uuid store_id FK
        uuid category_id FK
        text name
        text slug
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
    }

    PRODUCT {
        uuid id PK
        uuid store_id FK
        text external_product_id
        text sku
        text name
        text description
        uuid category_id FK
        char currency
        bigint cost_minor
        bigint price_minor
        uuid image_file_id FK
        text status
        text source
        jsonb metadata
        timestamptz created_at
        timestamptz updated_at
        timestamptz deleted_at
    }

    AUDIENCE_PROFILE {
        uuid id PK
        uuid store_id FK
        int version
        text status
        boolean is_current
        uuid[] niche_ids
        text[] languages
        text notes
        uuid created_by
        timestamptz created_at
        timestamptz updated_at
    }

    AUDIENCE_SEGMENT {
        uuid id PK
        uuid store_id FK
        uuid audience_profile_id FK
        text label
        jsonb locations
        int age_min
        int age_max
        text[] genders
        text[] interests
        text[] languages
        timestamptz created_at
    }

    FEEDBACK_ITEM {
        uuid id PK
        uuid store_id FK
        uuid audience_profile_id FK
        text source
        uuid stored_file_id FK
        text text
        text language
        text sentiment
        timestamptz captured_at
        timestamptz created_at
    }

    PRODUCT_CONCEPT {
        uuid id PK
        uuid store_id FK
        uuid source_idea_id FK
        text name
        text description
        uuid category_id FK
        uuid niche_id FK
        bigint price_minor
        bigint cost_minor
        char currency
        int gross_margin_bp
        uuid image_file_id FK
        text status
        int version
        uuid created_by
        timestamptz created_at
        timestamptz updated_at
        timestamptz deleted_at
    }

    SUFFICIENCY_CHECK {
        uuid id PK
        uuid store_id FK
        uuid product_concept_id FK
        text sales_history_status
        text audience_status
        text cost_price_status
        text competitive_data_status
        text overall_status
        jsonb blocking_reasons
        timestamptz checked_at
        timestamptz created_at
    }

    SCORING_MODEL {
        uuid id PK
        uuid store_id FK
        text key
        int version
        text name
        text description
        jsonb weights
        jsonb parameters
        boolean is_active
        timestamptz effective_from
        timestamptz created_at
        timestamptz updated_at
    }

    EVALUATION {
        uuid id PK
        uuid store_id FK
        uuid product_concept_id FK
        uuid scoring_model_id FK
        int model_version
        numeric score
        smallint score_scale
        text confidence
        boolean is_reliable
        uuid sufficiency_check_id FK
        jsonb input_snapshot
        timestamptz evaluated_at
        timestamptz created_at
    }

    SCORE_FACTOR {
        uuid id PK
        uuid store_id FK
        uuid evaluation_id FK
        text factor_key
        text factor_label
        text direction
        numeric contribution
        text explanation
        jsonb evidence
        timestamptz created_at
    }

    GENERATION_RUN {
        uuid id PK
        uuid store_id FK
        uuid requested_by
        text model_version
        jsonb input_snapshot
        int requested_count
        int returned_count
        text status
        text error_message
        timestamptz started_at
        timestamptz finished_at
        timestamptz created_at
    }

    PRODUCT_IDEA {
        uuid id PK
        uuid store_id FK
        uuid generation_run_id FK
        text name
        text description
        uuid category_id FK
        uuid niche_id FK
        text rationale
        text state
        text dismissed_reason
        uuid converted_concept_id FK
        text model_version
        timestamptz created_at
        timestamptz updated_at
    }

    IDEA_EVIDENCE {
        uuid id PK
        uuid store_id FK
        uuid product_idea_id FK
        text evidence_type
        text claim
        text source_name
        text source_url
        timestamptz source_published_at
        timestamptz retrieved_at
        numeric confidence
        timestamptz created_at
    }

    PAGE_TEMPLATE {
        uuid id PK
        text key
        int version
        text name
        boolean is_active
        jsonb schema
        timestamptz created_at
        timestamptz updated_at
    }

    LANDING_PAGE {
        uuid id PK
        uuid store_id FK
        uuid product_concept_id FK
        uuid test_id FK
        text slug UK
        text status
        uuid template_id FK
        uuid current_version_id FK
        uuid published_version_id FK
        uuid order_channel_id FK
        text language
        char currency
        text published_url
        timestamptz published_at
        timestamptz created_at
        timestamptz updated_at
        timestamptz deleted_at
    }

    PAGE_VERSION {
        uuid id PK
        uuid store_id FK
        uuid landing_page_id FK
        int version
        jsonb content
        bigint price_minor
        char currency
        uuid[] image_file_ids
        uuid order_channel_id FK
        text generated_by
        text model_version
        uuid created_by
        timestamptz created_at
    }

    POST {
        uuid id PK
        uuid store_id FK
        uuid test_id FK
        uuid product_concept_id FK
        uuid product_id FK
        text name
        text slug UK
        jsonb text_content
        text cta_text
        text cta_type
        uuid order_channel_id FK
        text status
        jsonb platform_context
        text published_url
        timestamptz published_at
        uuid created_by
        timestamptz created_at
        timestamptz updated_at
        timestamptz deleted_at
    }

    CREATIVE {
        uuid id PK
        uuid store_id FK
        text source
        text type
        uuid stored_file_id FK
        text external_url
        uuid content_generation_job_id FK
        int width
        int height
        int duration_ms
        text aspect_ratio
        text alt_text
        text prompt
        text model_version
        text status
        text approval_state
        jsonb metadata
        timestamptz created_at
        timestamptz updated_at
        timestamptz deleted_at
    }

    CREATIVE_VARIANT {
        uuid id PK
        uuid store_id FK
        uuid creative_id FK
        uuid stored_file_id FK
        text external_url
        int width
        int height
        text aspect_ratio
        text format
        int bitrate_kbps
        int duration_ms
        boolean is_primary
        jsonb metadata
        timestamptz created_at
    }

    POST_CREATIVE {
        uuid id PK
        uuid store_id FK
        uuid post_id FK
        uuid creative_id FK
        int position
        boolean is_primary
        jsonb overlay_text
        timestamptz created_at
    }

    ORDER_CHANNEL {
        uuid id PK
        uuid store_id FK
        uuid landing_page_id FK
        uuid post_id FK
        text type
        text whatsapp_number
        text whatsapp_message_template
        jsonb cod_form_schema
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
    }

    TEST {
        uuid id PK
        uuid store_id FK
        uuid product_concept_id FK
        uuid landing_page_id FK
        uuid post_id FK
        text name
        text status
        text primary_conversion
        char currency
        bigint total_budget_minor
        bigint daily_budget_minor
        bigint spend_minor
        timestamptz planned_start_at
        timestamptz planned_end_at
        timestamptz actual_start_at
        timestamptz actual_end_at
        uuid created_by
        timestamptz created_at
        timestamptz updated_at
    }

    TEST_EXTENSION {
        uuid id PK
        uuid store_id FK
        uuid test_id FK
        timestamptz previous_end_at
        timestamptz new_end_at
        bigint added_budget_minor
        char currency
        text reason
        uuid approved_by
        timestamptz created_at
    }

    CAMPAIGN {
        uuid id PK
        uuid store_id FK
        uuid test_id FK
        text provider
        text external_campaign_id
        text name
        text objective
        text status
        text budget_type
        bigint budget_minor
        char currency
        timestamptz start_at
        timestamptz end_at
        uuid created_by
        timestamptz created_at
        timestamptz updated_at
    }

    AD_SET {
        uuid id PK
        uuid store_id FK
        uuid campaign_id FK
        text external_adset_id
        text name
        text status
        jsonb targeting
        text budget_type
        bigint budget_minor
        char currency
        timestamptz start_at
        timestamptz end_at
        timestamptz created_at
        timestamptz updated_at
    }

    AD_VARIATION {
        uuid id PK
        uuid store_id FK
        uuid adset_id FK
        text external_ad_id
        text name
        text copy_text
        text headline
        text description
        uuid creative_file_id FK
        uuid primary_creative_id FK
        uuid post_id FK
        text destination_url
        text status
        text rejection_reason
        timestamptz created_at
        timestamptz updated_at
    }

    TRACKING_LINK {
        uuid id PK
        uuid store_id FK
        uuid test_id FK
        uuid campaign_id FK
        uuid adset_id FK
        uuid ad_variation_id FK
        uuid landing_page_id FK
        uuid post_id FK
        text token UK
        text utm_source
        text utm_medium
        text utm_campaign
        text utm_content
        text utm_term
        text destination_url
        timestamptz created_at
    }

    PUBLICATION_ATTEMPT {
        uuid id PK
        uuid store_id FK
        uuid campaign_id FK
        uuid adset_id FK
        uuid ad_variation_id FK
        text provider
        int attempt_number
        text status
        text external_id
        jsonb request_payload
        jsonb response_payload
        text error_code
        text error_message
        uuid submitted_by
        timestamptz submitted_at
        timestamptz created_at
    }

    TRACKING_SESSION {
        uuid id PK
        uuid store_id FK
        uuid landing_page_id FK
        uuid post_id FK
        uuid test_id FK
        uuid campaign_id FK
        text first_utm_source
        text first_utm_medium
        text first_utm_campaign
        text first_utm_content
        text first_utm_term
        text referrer
        text user_agent
        char ip_hash
        text consent_state
        timestamptz started_at
        timestamptz last_seen_at
        timestamptz created_at
    }

    EVENT {
        uuid id PK
        uuid store_id FK
        uuid event_id UK
        uuid tracking_session_id FK
        uuid test_id FK
        uuid product_id FK
        uuid campaign_id FK
        uuid adset_id FK
        uuid ad_variation_id FK
        uuid post_id FK
        text event_type
        text source
        text url
        text referrer
        timestamptz occurred_at
        timestamptz received_at
        boolean is_bot
        jsonb properties
        timestamptz created_at
    }

    ORDER {
        uuid id PK
        uuid store_id FK
        text origin
        text external_order_id
        text order_number
        uuid test_id FK
        text test_phase
        text status
        char currency
        bigint subtotal_minor
        bigint shipping_minor
        bigint discount_minor
        bigint total_minor
        text customer_name
        text customer_phone
        bytea customer_address_enc
        uuid landing_page_id FK
        uuid post_id FK
        uuid campaign_id FK
        uuid tracking_session_id FK
        uuid import_batch_id FK
        char dedupe_hash
        timestamptz placed_at
        timestamptz imported_at
        timestamptz created_at
        timestamptz updated_at
    }

    ORDER_ITEM {
        uuid id PK
        uuid store_id FK
        uuid order_id FK
        uuid product_id FK
        text product_external_id
        text product_name_snapshot
        text sku_snapshot
        int quantity
        bigint unit_price_minor
        bigint line_total_minor
        char currency
        jsonb metadata
        timestamptz created_at
    }

    DEPOSIT {
        uuid id PK
        uuid store_id FK
        uuid order_id FK
        uuid test_id FK
        text status
        bigint amount_minor
        char currency
        text method
        uuid evidence_file_id FK
        text external_payment_id
        uuid verified_by
        timestamptz verified_at
        timestamptz created_at
        timestamptz updated_at
    }

    ATTRIBUTION {
        uuid id PK
        uuid store_id FK
        text subject_type
        uuid subject_id
        uuid test_id FK
        uuid campaign_id FK
        uuid adset_id FK
        uuid ad_variation_id FK
        uuid post_id FK
        text model
        int window_seconds
        boolean is_attributed
        numeric confidence
        timestamptz resolved_at
        timestamptz created_at
    }

    METRIC_SNAPSHOT {
        uuid id PK
        uuid store_id FK
        uuid test_id FK
        text provider
        uuid campaign_id FK
        uuid adset_id FK
        uuid ad_variation_id FK
        timestamptz period_start
        timestamptz period_end
        timestamptz snapshot_at
        char currency
        bigint spend_minor
        bigint impressions
        bigint reach
        numeric frequency
        bigint clicks
        numeric ctr
        bigint cpc_minor
        bigint cpm_minor
        bigint engagement
        bigint platform_conversions
        bigint cost_per_conversion_minor
        jsonb raw
        timestamptz created_at
    }

    OPTIMIZATION_RULE_SET {
        uuid id PK
        uuid store_id FK
        text scope
        uuid campaign_id FK
        int version
        boolean is_active
        int min_impressions
        int min_clicks
        int min_conversions
        numeric ctr_floor
        bigint cpc_ceiling_minor
        bigint cost_per_conversion_ceiling_minor
        jsonb rules
        uuid created_by
        timestamptz created_at
        timestamptz updated_at
    }

    PERFORMANCE_FINDING {
        uuid id PK
        uuid store_id FK
        uuid campaign_id FK
        uuid adset_id FK
        uuid ad_variation_id FK
        uuid rule_set_id FK
        text status
        text metric_key
        numeric observed_value
        numeric threshold_value
        text reason_code
        timestamptz data_window_start
        timestamptz data_window_end
        timestamptz evaluated_at
        timestamptz created_at
    }

    OPTIMIZATION_RECOMMENDATION {
        uuid id PK
        uuid store_id FK
        uuid finding_id FK
        uuid campaign_id FK
        uuid adset_id FK
        uuid ad_variation_id FK
        text action
        text rationale
        jsonb proposed_changes
        jsonb expected_impact
        bigint budget_impact_minor
        char currency
        text status
        timestamptz created_at
        timestamptz updated_at
    }

    OPTIMIZATION_ACTION {
        uuid id PK
        uuid store_id FK
        uuid recommendation_id FK
        uuid campaign_id FK
        uuid adset_id FK
        uuid ad_variation_id FK
        text action_type
        text actor_type
        uuid actor_user_id FK
        jsonb before_state
        jsonb after_state
        text reason
        text external_reference
        text status
        timestamptz executed_at
        timestamptz reverted_at
        timestamptz created_at
    }

    BUDGET_POLICY {
        uuid id PK
        uuid store_id FK
        uuid test_id FK
        uuid campaign_id FK
        bigint total_cap_minor
        bigint daily_cap_minor
        char currency
        text enforcement
        boolean is_active
        uuid created_by
        timestamptz created_at
        timestamptz updated_at
    }

    ALERT {
        uuid id PK
        uuid store_id FK
        text type
        text severity
        text title
        text message
        text related_type
        uuid related_id
        text status
        uuid acknowledged_by FK
        timestamptz resolved_at
        timestamptz created_at
        timestamptz updated_at
    }

    DECISION_RULE_SET {
        uuid id PK
        uuid store_id FK
        uuid category_id FK
        int version
        boolean is_active
        bigint min_spend_minor
        int min_clicks
        int min_conversions
        int min_confirmed_deposits
        numeric min_conversion_rate
        bigint max_cost_per_conversion_minor
        jsonb rules
        uuid created_by
        timestamptz created_at
        timestamptz updated_at
    }

    TEST_RESULT_SNAPSHOT {
        uuid id PK
        uuid store_id FK
        uuid test_id FK
        timestamptz period_start
        timestamptz period_end
        char currency
        bigint spend_minor
        bigint impressions
        bigint clicks
        bigint tracked_conversions
        bigint confirmed_deposits
        numeric conversion_rate
        bigint cost_per_conversion_minor
        numeric data_completeness
        uuid[] source_metric_snapshot_ids
        timestamptz captured_at
        timestamptz created_at
    }

    VERDICT {
        uuid id PK
        uuid store_id FK
        uuid test_id FK
        uuid result_snapshot_id FK
        uuid decision_rule_set_id FK
        text outcome
        boolean is_conclusive
        text primary_reason
        jsonb limitations
        jsonb rule_trace
        timestamptz created_at
    }

    INVESTMENT_PROFILE {
        uuid id PK
        uuid store_id FK
        uuid test_id FK
        int version
        bigint unit_cost_minor
        bigint selling_price_minor
        bigint fulfillment_cost_minor
        int payment_fee_bp
        bigint available_budget_minor
        int target_margin_bp
        int supplier_moq
        int lead_time_days
        char currency
        boolean is_current
        uuid created_by
        timestamptz created_at
        timestamptz updated_at
    }

    INVESTMENT_RECOMMENDATION {
        uuid id PK
        uuid store_id FK
        uuid test_id FK
        uuid investment_profile_id FK
        int version
        text summary
        jsonb assumptions_snapshot
        boolean is_current
        uuid created_by
        timestamptz created_at
        timestamptz updated_at
    }

    DEMAND_ESTIMATE {
        uuid id PK
        uuid store_id FK
        uuid investment_recommendation_id FK
        int low_units
        int base_units
        int high_units
        jsonb assumptions
        text confidence
        timestamptz created_at
    }

    UNIT_ECONOMICS {
        uuid id PK
        uuid store_id FK
        uuid investment_recommendation_id FK
        bigint contribution_margin_minor
        numeric break_even_units
        bigint cac_minor
        jsonb formulas
        boolean is_negative_margin
        timestamptz created_at
    }

    QUANTITY_SCENARIO {
        uuid id PK
        uuid store_id FK
        uuid investment_recommendation_id FK
        text label
        int quantity
        bigint inventory_cost_minor
        int expected_units_sold_low
        int expected_units_sold_high
        bigint revenue_low_minor
        bigint revenue_high_minor
        bigint profit_low_minor
        bigint profit_high_minor
        numeric sell_through_low
        numeric sell_through_high
        text overstock_risk
        text stockout_risk
        boolean is_feasible
        text infeasibility_reason
        timestamptz created_at
    }

    COUNTRY {
        char code PK
        text name
        boolean is_active
    }

    CURRENCY {
        char code PK
        text name
        smallint minor_unit
        boolean is_active
    }

    LANGUAGE {
        text code PK
        text name
        text direction
        boolean is_active
    }

    AD_PLATFORM {
        text code PK
        text name
        boolean is_active
    }

    EVENT_TYPE {
        text code PK
        text description
        boolean is_active
    }

    STORE ||--o{ USER : "owned_by"
    USER ||--o{ AUDIT_LOG : "acts"
    STORE ||--o{ AUDIT_LOG : "scoped"
    STORE ||--o{ ASYNC_JOB : "scoped"
    STORE ||--o{ STORE_CONNECTION : "has"
    STORE ||--o{ AD_ACCOUNT_CONNECTION : "has"
    STORE ||--o{ CONTENT_PROVIDER : "has"
    CONTENT_PROVIDER ||--o{ CONTENT_GENERATION_JOB : "runs"
    CONTENT_GENERATION_JOB ||--o{ CREATIVE : "produces"
    STORED_FILE ||--o{ CREATIVE : "backs"
    STORED_FILE ||--o{ CREATIVE_VARIANT : "backs"
    CREATIVE ||--o{ CREATIVE_VARIANT : "has"
    CREATIVE ||--o{ POST_CREATIVE : "used_in"
    STORE ||--o{ IMPORT_BATCH : "imports"
    IMPORT_BATCH ||--o{ IMPORT_ROW : "contains"
    IMPORT_ROW ||--o{ IMPORT_ISSUE : "has"
    IMPORT_BATCH ||--o{ ORDER : "creates"
    IMPORT_ROW ||--o{ ORDER : "creates_row"
    CATEGORY ||--o{ CATEGORY : "parent"
    CATEGORY ||--o{ NICHE : "has"
    STORE ||--o{ NICHE : "has"
    STORE ||--o{ PRODUCT : "catalog"
    CATEGORY ||--o{ PRODUCT : "classified"
    STORED_FILE ||--o{ PRODUCT : "image"
    STORE ||--o{ AUDIENCE_PROFILE : "defines"
    AUDIENCE_PROFILE ||--o{ AUDIENCE_SEGMENT : "contains"
    AUDIENCE_PROFILE ||--o{ FEEDBACK_ITEM : "informs"
    STORED_FILE ||--o{ FEEDBACK_ITEM : "file"
    STORE ||--o{ PRODUCT_CONCEPT : "evaluates"
    PRODUCT_CONCEPT ||--o{ SUFFICIENCY_CHECK : "assessed"
    PRODUCT_CONCEPT ||--o{ EVALUATION : "scored"
    SCORING_MODEL ||--o{ EVALUATION : "defines"
    SUFFICIENCY_CHECK ||--o{ EVALUATION : "gates"
    EVALUATION ||--o{ SCORE_FACTOR : "explained"
    PRODUCT_IDEA ||--o{ PRODUCT_CONCEPT : "converts_to"
    GENERATION_RUN ||--o{ PRODUCT_IDEA : "produces"
    PRODUCT_IDEA ||--o{ IDEA_EVIDENCE : "supported"
    PAGE_TEMPLATE ||--o{ LANDING_PAGE : "renders"
    PRODUCT_CONCEPT ||--o{ LANDING_PAGE : "basis"
    LANDING_PAGE ||--o{ PAGE_VERSION : "versions"
    ORDER_CHANNEL }o--|| LANDING_PAGE : "configures_lp"
    ORDER_CHANNEL }o--|| POST : "configures_post"
    STORE ||--o{ TEST : "runs"
    PRODUCT_CONCEPT ||--o{ TEST : "tests"
    TEST ||--o| LANDING_PAGE : "uses_lp"
    TEST ||--o| POST : "uses_post"
    TEST ||--o{ TEST_EXTENSION : "extends"
    POST ||--o{ POST_CREATIVE : "contains"
    TEST ||--o{ POST : "has"
    TEST ||--o{ CAMPAIGN : "runs"
    CAMPAIGN ||--o{ AD_SET : "contains"
    AD_SET ||--o{ AD_VARIATION : "contains"
    AD_VARIATION }o--|| POST : "targets"
    CREATIVE ||--o{ AD_VARIATION : "primary"
    TEST ||--o{ TRACKING_LINK : "tags"
    LANDING_PAGE ||--o{ TRACKING_LINK : "tags"
    POST ||--o{ TRACKING_LINK : "tags"
    CAMPAIGN ||--o{ TRACKING_LINK : "tags"
    AD_SET ||--o{ TRACKING_LINK : "tags"
    AD_VARIATION ||--o{ TRACKING_LINK : "tags"
    CAMPAIGN ||--o{ PUBLICATION_ATTEMPT : "submits"
    AD_SET ||--o{ PUBLICATION_ATTEMPT : "submits"
    AD_VARIATION ||--o{ PUBLICATION_ATTEMPT : "submits"
    TRACKING_SESSION ||--o{ EVENT : "contains"
    EVENT }o--|| ATTRIBUTION : "resolved_event"
    ORDER }o--|| ATTRIBUTION : "resolved_order"
    ORDER ||--o| DEPOSIT : "has"
    CAMPAIGN ||--o{ METRIC_SNAPSHOT : "measured_c"
    AD_SET ||--o{ METRIC_SNAPSHOT : "measured_s"
    AD_VARIATION ||--o{ METRIC_SNAPSHOT : "measured_v"
    ORDER ||--o{ ORDER_ITEM : "contains"
    PRODUCT ||--o{ ORDER_ITEM : "item"
    LANDING_PAGE ||--o{ ORDER : "converts_lp"
    POST ||--o{ ORDER : "converts_post"
    TEST ||--o{ ORDER : "tags"
    CAMPAIGN ||--o{ ORDER : "tags"
    OPTIMIZATION_RULE_SET ||--o{ PERFORMANCE_FINDING : "evaluates"
    PERFORMANCE_FINDING ||--o{ OPTIMIZATION_RECOMMENDATION : "proposes"
    OPTIMIZATION_RECOMMENDATION ||--o{ OPTIMIZATION_ACTION : "executes"
    TEST ||--o{ BUDGET_POLICY : "constrains_t"
    CAMPAIGN ||--o{ BUDGET_POLICY : "constrains_c"
    TEST ||--o{ TEST_RESULT_SNAPSHOT : "snapshots"
    TEST_RESULT_SNAPSHOT ||--o{ VERDICT : "supports"
    DECISION_RULE_SET ||--o{ VERDICT : "evaluates"
    TEST ||--o{ VERDICT : "receives"
    TEST ||--o{ INVESTMENT_PROFILE : "configures"
    INVESTMENT_PROFILE ||--o{ INVESTMENT_RECOMMENDATION : "produces"
    INVESTMENT_RECOMMENDATION ||--o| DEMAND_ESTIMATE : "estimates"
    INVESTMENT_RECOMMENDATION ||--o| UNIT_ECONOMICS : "computes"
    INVESTMENT_RECOMMENDATION ||--o{ QUANTITY_SCENARIO : "proposes"
```

## Modeling Decisions Applied

- **Orders are unified.** Imported sales and COD submissions share the `Order` and `OrderItem` model. Each order records its origin and is tagged as `before_test`, `during_test`, or `after_test`, with an optional test reference.
- **Ads are nested under ad sets.** The hierarchy is `Campaign → AdSet → AdVariation`.
- **Excluded entities.** `Membership`, `AiRun`, `SalesRecord`, and `CampaignTargeting` are not modeled. Roles remain on `User`, AI provenance is stored on the generated records themselves, `SalesRecord` is replaced by `Order`, and targeting lives on `AdSet`.
- **`Test` is the central aggregate.** Landing pages, campaigns, verdicts, extensions, and investment outputs attach to a test.
- **Versioning is append-only.** Audience profiles, page versions, scoring models, rule sets, investment profiles, and investment recommendations are immutable versions referenced by their outputs.
- **Investment outputs are recommendation-scoped.** `InvestmentProfile` holds versioned inputs; `InvestmentRecommendation` is the computed version that owns `DemandEstimate`, `UnitEconomics`, and `QuantityScenario`.
- **Database conventions.** PostgreSQL with UUIDv7 primary keys; money is stored in minor units with ISO 4217 currency; a single currency per store is assumed for the MVP.
