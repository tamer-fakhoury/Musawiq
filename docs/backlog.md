# Musawiq MVP Backlog

Source: `docs/Requirements.md` (FRs) and `docs/Specifications.md` (entities + OOP).
MVP cut: Slices A + B + C + D + E, plus FR-4.2.5 (recommendations only).

---

# Phase 0 — Database Construction (must be first)

Build the schema before any application feature. Each task is complete only when the migration
runs clean on a fresh database, rolls back cleanly, and matches `## Entity Fields` and the
`## ERD Diagram` in `Specifications.md`.

**Ground rules**
- `docs/Specifications.md` is the source of truth. No table, column, index, or constraint may exist that is not derivable from it.
- PostgreSQL 18; native `uuidv7()`; `NULLS NOT DISTINCT` available.
- Alembic, SQL-first (`op.execute`). Autogenerate is never the source of truth.
- Naming and layout: see `docs/CONVENTIONS.md`. Physical tables are **plural** (`stores`, `orders`, `users`); entity names in prose are singular.
- Enum-like values are `text` + `CHECK`, never native `ENUM`.
- Tenant tables carry `store_id`; reference data does not.
- Money `*_minor bigint` + `currency char(3)`; rate inputs `*_bp int`; computed metrics `numeric(12,6)`.
- JSONB only for configuration, payloads, and snapshots; always carries `schema_version`.
- No application code writes to a table before that table's owning DB task is accepted.
- **Cross-domain FKs are deferred to DB-0.13.** A task creates FKs only to tables that already exist; references to future tables (e.g. `orders.test_id`, `products.category_id`, `landing_pages`) are added during the DB-0.13 integrity pass. Do not fail a task for those missing FKs.

**Definition of Done (applies to every DB task)**
1. Migration `up` and `down` both run cleanly on an empty database.
2. `information_schema` diff against `Specifications.md` for the tables in scope is empty.
3. All CHECK, UNIQUE, FK, and NOT NULL constraints exist and are named.
4. Indexes exist for the access patterns the spec calls out; `EXPLAIN` shows no sequential scan on the intended paths.
5. A test asserts the task's constraints actually reject invalid rows.
6. RLS policy is attached where the table is tenant-owned (from DB-0.15).
7. The migration is committed with the parity/regression evidence that guards it.

## Module DB — Schema Construction (P0)

### DB-0.1 Migration tooling and project baseline
**TASK:** Configure a versioned migration tool with an ordered migration directory, one migration per DB task, committed generated SQL, and a `schema_migrations` tracking table.
**ACCEPTANCE CRITERIA:**
- `up` and `down` run cleanly from empty to empty.
- Local verification (`scripts/verify_db.py`) applies all migrations to a throwaway database. (No CI host in this project.)
- Credentials come from environment variables only.
- Naming and folder conventions are documented in `docs/CONVENTIONS.md`.
- Expected baseline result: `PARITY OK (0 declared tables, 0 extensions, 0 functions)`, `5 passed, 2 skipped` (RLS tests skip until DB-0.15), `EMPTY OK`, `VERIFY OK`.

### DB-0.2 Extensions, conventions, and shared primitives
**TASK:** On PostgreSQL 18, rely on native `uuidv7()` for all `id` defaults; install `citext` and `pg_trgm`; add `fn_touch_updated_at()` for mutable tables and `fn_block_mutation()` for append-only tables.
**ACCEPTANCE CRITERIA:**
- `citext` and `pg_trgm` installed via the migration; `pgcrypto` only if a hash function is needed.
- `uuidv7()` is available natively (no plpgsql shim) and returns a version-7 UUID.
- `fn_touch_updated_at()` exists in `public`, `LANGUAGE plpgsql`, and sets `NEW.updated_at = now()`.
- `fn_block_mutation()` exists in `public`, `LANGUAGE plpgsql`, and raises an exception on `UPDATE` or `DELETE`.
- Both functions are proven by tests that create a temporary table, attach the triggers, assert the behaviour, then roll back.
- `scripts/schema_manifest.py` declares both extensions and both functions; parity passes.
- `up`/`down` reversible; `down` drops the functions and does not drop extensions still needed by later revisions (keep `citext`/`pg_trgm` installed on downgrade).
- No tables created by this task.

### DB-0.3 Reference data tables and seed
**TASK:** Create `countries(code,name,is_active)`, `currencies(code,name,minor_unit,is_active)`, `languages(code,name,direction,is_active)`, `ad_platforms(code,name,is_active)`, `event_types(code,description,is_active)` and seed them.
**ACCEPTANCE CRITERIA:**
- `languages.direction` restricted to `ltr | rtl`.
- Canonical event types seeded: `page_view`, `product_view`, `cta_click`, `whatsapp_click`, `cod_form_start`, `cod_order_submitted`, `deposit_confirmed`.
- `currencies.minor_unit` populated for every seeded currency.
- `ad_platforms` seeded for the MVP platforms (decision D1).
- Seed is idempotent (`ON CONFLICT DO NOTHING`) and re-runnable.

### DB-0.4 Identity & tenancy tables
**TASK:** Create `stores(id,owner_user_id,name,slug,status,default_currency,default_language,timezone,country_code,onboarding_status,settings,deleted_at,created_at,updated_at)`, `users(id,email,password_hash,full_name,phone,locale,timezone,role,status,email_verified_at,last_login_at,auth_provider,auth_subject,deleted_at,created_at,updated_at)`, `audit_logs(id,store_id,actor_user_id,actor_type,action,target_type,target_id,before,after,metadata,ip_hash,user_agent,correlation_id,created_at)`, `async_jobs(id,store_id,job_type,state,idempotency_key,payload,result,progress_current,progress_total,attempt_count,max_attempts,error_code,error_message,correlation_id,scheduled_at,started_at,finished_at,created_at,updated_at)`.
**ACCEPTANCE CRITERIA:**
- `stores.owner_user_id` FK to `users` and UNIQUE (1 store per user for MVP).
- `stores.slug` UNIQUE; `users.email` UNIQUE (citext); partial UNIQUE on `(auth_provider, auth_subject)` where both not null.
- CHECKs on `stores.status`, `stores.onboarding_status`, `users.role` (`owner|manager|analyst`), `users.status`, `async_jobs.job_type`, `async_jobs.state`, `audit_logs.actor_type`.
- `async_jobs.idempotency_key` UNIQUE where not null; `async_jobs.store_id` is nullable (system jobs).
- `audit_logs` is append-only: no `updated_at`, mutation blocked by `trg_audit_logs_block_mutation`.
- FKs to `currencies`, `languages`, `countries`.
- `fn_touch_updated_at` triggers on `stores`, `users`, `async_jobs`.

### DB-0.5 Integrations & data ingestion tables
**TASK:** Create `store_connections(provider,external_store_id,status,scopes,access_token_encrypted,refresh_token_encrypted,token_expires_at,last_synced_at,metadata)`, `ad_account_connections(provider,external_account_id,account_name,status,scopes,access_token_encrypted,refresh_token_encrypted,token_expires_at,last_synced_at,metadata)`, `content_providers(store_id,code,name,media_types,auth_config_encrypted,rate_limits,pricing,capabilities,enabled,is_default)`, `content_generation_jobs(content_provider_id,type,prompt,negative_prompt,params,status,requested_by,result_creative_ids,cost_minor,currency,error_code,error_message,async_job_id,started_at,finished_at)`, `stored_files(purpose,original_filename,mime_type,size_bytes,checksum_sha256,storage_provider,storage_key,status,uploaded_by_user_id,metadata,deleted_at)`, `import_batches(source_type,stored_file_id,store_connection_id,column_mapping_id,status,strict_mode,date_range_start,date_range_end,total_rows,valid_rows,invalid_rows,duplicate_rows,imported_rows,skipped_rows,error_report_file_id,started_at,completed_at,created_by)`, `column_mappings(name,source_type,mapping,is_default,created_by)`, `import_rows(import_batch_id,row_number,raw_data,normalized_data,status,issue_count,created_order_id)`, `import_issues(import_batch_id,import_row_id,row_number,field_name,issue_code,severity,message,raw_value)`, `products(external_product_id,sku,name,description,category_id,currency,cost_minor,price_minor,image_file_id,status,source,metadata,deleted_at)`, `orders(origin,external_order_id,order_number,test_id,test_phase,status,currency,subtotal_minor,shipping_minor,discount_minor,total_minor,customer_name,customer_phone,customer_address_enc,landing_page_id,post_id,campaign_id,tracking_session_id,import_batch_id,dedupe_hash,placed_at,imported_at)`, `order_items(order_id,product_id,product_external_id,product_name_snapshot,sku_snapshot,quantity,unit_price_minor,line_total_minor,currency,metadata)`.
**ACCEPTANCE CRITERIA:**
- All tables carry `store_id` except global `content_providers` (nullable `store_id`).
- UNIQUE: `store_connections(store_id, provider)`, `ad_account_connections(store_id, provider, external_account_id)`, `content_providers(store_id, code)` and `(code)` where `store_id` is null, `products(store_id, external_product_id)` where not null, `products(store_id, sku)` where not null, `orders(store_id, external_order_id)` where not null, `orders(store_id, dedupe_hash)` where not null, `import_rows(import_batch_id, row_number)`.
- `import_batches` CHECK requires `stored_file_id` for `csv` and `store_connection_id` for `store_connection`.
- `order_items.quantity > 0`; `orders.origin` CHECK (`imported|cod`); `orders.test_phase` CHECK (`before_test|during_test|after_test`); `orders.status` CHECK.
- `stored_files.purpose` and `.status` CHECKs; `content_generation_jobs.status` CHECK.
- Indexes: `orders(store_id, test_id, test_phase)`, `orders(store_id, placed_at)`, `products(store_id, status)`, `import_rows(import_batch_id, row_number)`.

### DB-0.6 Audience & store context tables
**TASK:** Create `category(parent_id,name,slug,is_active,sort_order)`, `niche(category_id,store_id,name,slug,is_active)`, `audience_profile(version,status,is_current,niche_ids,languages,notes,created_by)`, `audience_segment(audience_profile_id,label,locations,age_min,age_max,genders,interests,languages)`, `feedback_item(audience_profile_id,source,stored_file_id,text,language,sentiment,captured_at)`.
**ACCEPTANCE CRITERIA:**
- `category.parent_id` self-FK; `category.slug` UNIQUE; partial UNIQUE `niche(store_id, slug)` where `store_id` is not null.
- `audience_profile` UNIQUE `(store_id, version)` and partial UNIQUE `(store_id)` where `is_current`.
- `audience_segment` CHECK `age_min <= age_max`.
- CHECKs on `audience_profile.status`, `feedback_item.source` (`manual|file`), `feedback_item.sentiment`.
- `locations`, `interests` stored as JSONB arrays with a `schema_version` key.

### DB-0.7 Product evaluation tables
**TASK:** Create `product_concept(source_idea_id,name,description,category_id,niche_id,price_minor,cost_minor,currency,gross_margin_bp,image_file_id,status,version,created_by,deleted_at)`, `sufficiency_check(product_concept_id,sales_history_status,audience_status,cost_price_status,competitive_data_status,overall_status,blocking_reasons,checked_at)`, `evaluation(product_concept_id,scoring_model_id,model_version,score,score_scale,confidence,is_reliable,sufficiency_check_id,input_snapshot,evaluated_at)`, `score_factor(evaluation_id,factor_key,factor_label,direction,contribution,explanation,evidence)`, `scoring_model(store_id,key,version,name,description,weights,parameters,is_active,effective_from)`.
**ACCEPTANCE CRITERIA:**
- `product_concept.status` CHECK (`draft|evaluated|selected|archived`); `deleted_at` soft delete; `version int`.
- `evaluation.score` nullable (NULL means unavailable, never 0); `score_scale` default 100; `confidence` CHECK (`high|medium|low`).
- `score_factor.direction` CHECK (`positive|negative|neutral`); `contribution numeric(7,4)`.
- `scoring_model` UNIQUE `(key, version)`; nullable `store_id` for platform default.
- Status CHECKs on all `*_status` columns (`available|missing|stale|insufficient`) and `overall_status` (`sufficient|insufficient`).
- Indexes: `evaluation(product_concept_id, evaluated_at DESC)`, `score_factor(evaluation_id)`.

### DB-0.8 Recommendations tables
**TASK:** Create `generation_run(requested_by,model_version,input_snapshot,requested_count,returned_count,status,error_message,started_at,finished_at)`, `product_idea(generation_run_id,name,description,category_id,niche_id,rationale,state,dismissed_reason,converted_concept_id,model_version)`, `idea_evidence(product_idea_id,evidence_type,claim,source_name,source_url,source_published_at,retrieved_at,confidence)`.
**ACCEPTANCE CRITERIA:**
- `generation_run.status` CHECK (`queued|running|succeeded|failed`).
- `product_idea.state` CHECK (`new|saved|dismissed|converted`).
- `idea_evidence.evidence_type` CHECK (`verified|hypothesis`) and CHECK (`evidence_type <> 'verified' OR source_url IS NOT NULL`).
- Deferred FK `product_concept.source_idea_id → product_idea.id` added.
- Indexes: `product_idea(store_id, state)`, `idea_evidence(product_idea_id)`.

### DB-0.9 Assets, posts, campaigns & tests tables
**TASK:** Create `landing_page(product_concept_id,test_id,slug,status,template_id,current_version_id,published_version_id,order_channel_id,language,currency,published_url,published_at,deleted_at)`, `page_version(landing_page_id,version,content,price_minor,currency,image_file_ids,order_channel_id,generated_by,model_version,created_by)`, `page_template(key,version,name,is_active,schema)`, `order_channel(landing_page_id,post_id,type,whatsapp_number,whatsapp_message_template,cod_form_schema,is_active)`, `post(test_id,product_concept_id,product_id,name,slug,text_content,cta_text,cta_type,order_channel_id,status,platform_context,published_url,published_at,created_by,deleted_at)`, `post_creative(post_id,creative_id,position,is_primary,overlay_text)`, `creative(source,type,stored_file_id,external_url,content_generation_job_id,width,height,duration_ms,aspect_ratio,alt_text,prompt,model_version,status,approval_state,metadata,deleted_at)`, `creative_variant(creative_id,stored_file_id,external_url,width,height,aspect_ratio,format,bitrate_kbps,duration_ms,is_primary,metadata)`, `test(product_concept_id,landing_page_id,post_id,name,status,primary_conversion,currency,total_budget_minor,daily_budget_minor,spend_minor,planned_start_at,planned_end_at,actual_start_at,actual_end_at,created_by)`, `test_extension(test_id,previous_end_at,new_end_at,added_budget_minor,currency,reason,approved_by)`, `campaign(test_id,provider,external_campaign_id,name,objective,status,budget_type,budget_minor,currency,start_at,end_at,created_by)`, `ad_set(campaign_id,external_adset_id,name,status,targeting,budget_type,budget_minor,currency,start_at,end_at)`, `ad_variation(adset_id,external_ad_id,name,copy_text,headline,description,creative_file_id,primary_creative_id,post_id,destination_url,status,rejection_reason)`, `tracking_link(test_id,campaign_id,adset_id,ad_variation_id,landing_page_id,post_id,token,utm_source,utm_medium,utm_campaign,utm_content,utm_term,destination_url)`, `publication_attempt(campaign_id,adset_id,ad_variation_id,provider,attempt_number,status,external_id,request_payload,response_payload,error_code,error_message,submitted_by,submitted_at)`.
**ACCEPTANCE CRITERIA:**
- `landing_page.slug` UNIQUE; `page_version` UNIQUE `(landing_page_id, version)`; `page_template` UNIQUE `(key, version)`; `tracking_link.token` UNIQUE.
- `post_creative` UNIQUE `(post_id, creative_id)` and `(post_id, position)`.
- `order_channel` CHECK: `type='whatsapp'` requires `whatsapp_number`, `type='cod'` requires `cod_form_schema`, plus page/post XOR.
- `test` CHECK: page/post XOR, or `status='draft'`; `primary_conversion` CHECK (`whatsapp_click|cod_order|deposit_confirmed`).
- `creative` and `creative_variant` CHECK (`stored_file_id` OR `external_url`).
- `ad_variation` CHECK (`post_id` OR `destination_url`); status CHECK.
- `publication_attempt` CHECK: exactly one of campaign/adset/ad_variation targeted.
- Indexes: `campaign(test_id, status)`, `ad_set(campaign_id)`, `ad_variation(adset_id, status)`, `landing_page(slug)`.

### DB-0.10 Measurement tables
**TASK:** Create `tracking_session(landing_page_id,test_id,campaign_id,first_utm_source,first_utm_medium,first_utm_campaign,first_utm_content,first_utm_term,referrer,user_agent,ip_hash,consent_state,started_at,last_seen_at)`, `event(event_id,tracking_session_id,test_id,product_id,campaign_id,adset_id,ad_variation_id,event_type,source,url,referrer,occurred_at,received_at,is_bot,properties)`, `deposit(order_id,test_id,status,amount_minor,currency,method,evidence_file_id,external_payment_id,verified_by,verified_at)`, `attribution(subject_type,subject_id,test_id,campaign_id,adset_id,ad_variation_id,model,window_seconds,is_attributed,confidence,resolved_at)`, `metric_snapshot(test_id,provider,campaign_id,adset_id,ad_variation_id,period_start,period_end,snapshot_at,currency,spend_minor,impressions,reach,frequency,clicks,ctr,cpc_minor,cpm_minor,engagement,platform_conversions,cost_per_conversion_minor,raw)`.
**ACCEPTANCE CRITERIA:**
- `event.event_id` UNIQUE (idempotent ingestion); `event.event_type` FK to `event_type`; `event.source` CHECK (`web|server`); append-only.
- `tracking_session.ip_hash char(64)`; `consent_state` CHECK (`unknown|granted|denied`).
- `attribution` UNIQUE `(subject_type, subject_id)`; `subject_type` CHECK (`event|order`); `model` CHECK (`last_touch|first_touch|direct`).
- `deposit.status` CHECK (`pending|confirmed|rejected`); `method` CHECK (`manual|payment_gateway`).
- `metric_snapshot` UNIQUE **NULLS NOT DISTINCT** `(campaign_id, adset_id, ad_variation_id, period_start, period_end)`.
- Indexes: `event(store_id, event_type, occurred_at)`, `event(tracking_session_id)`, `metric_snapshot(campaign_id, period_start)`, `deposit(order_id)`.

### DB-0.11 Optimization tables
**TASK:** Create `optimization_rule_set(store_id,scope,campaign_id,version,is_active,min_impressions,min_clicks,min_conversions,ctr_floor,cpc_ceiling_minor,cost_per_conversion_ceiling_minor,rules,created_by)`, `performance_finding(campaign_id,adset_id,ad_variation_id,rule_set_id,status,metric_key,observed_value,threshold_value,reason_code,data_window_start,data_window_end,evaluated_at)`, `optimization_recommendation(finding_id,campaign_id,adset_id,ad_variation_id,action,rationale,proposed_changes,expected_impact,budget_impact_minor,currency,status)`, `optimization_action(recommendation_id,campaign_id,adset_id,ad_variation_id,action_type,actor_type,actor_user_id,before_state,after_state,reason,external_reference,status,executed_at,reverted_at)`, `budget_policy(test_id,campaign_id,total_cap_minor,daily_cap_minor,currency,enforcement,is_active,created_by)`, `alert(type,severity,title,message,related_type,related_id,status,acknowledged_by,resolved_at)`.
**ACCEPTANCE CRITERIA:**
- `optimization_rule_set.scope` CHECK (`global|store|campaign`) with CHECK (`scope='campaign'` requires `campaign_id`); UNIQUE **NULLS NOT DISTINCT** `(store_id, scope, campaign_id, version)`.
- `performance_finding.status` CHECK (`underperforming|promising|insufficient_data`).
- `optimization_recommendation.action` CHECK (`pause|keep|reallocate|increase_budget|decrease_budget`); `status` CHECK (`pending|accepted|dismissed|executed|expired`).
- `optimization_action.actor_type` CHECK (`user|system`); `status` CHECK (`succeeded|failed|reverted`).
- `budget_policy` CHECK (at least one of `test_id`/`campaign_id`); `enforcement` CHECK (`hard|soft`).
- `alert.type` CHECK (`overspend|sync_failure|anomaly|publication_failure`); `severity` CHECK (`info|warning|critical`); `status` CHECK (`open|acknowledged|resolved`).

### DB-0.12 Decision & investment tables
**TASK:** Create `decision_rule_set(store_id,category_id,version,is_active,min_spend_minor,min_clicks,min_conversions,min_confirmed_deposits,min_conversion_rate,max_cost_per_conversion_minor,rules,created_by)`, `test_result_snapshot(test_id,period_start,period_end,currency,spend_minor,impressions,clicks,tracked_conversions,confirmed_deposits,conversion_rate,cost_per_conversion_minor,data_completeness,source_metric_snapshot_ids,captured_at)`, `verdict(test_id,result_snapshot_id,decision_rule_set_id,outcome,is_conclusive,primary_reason,limitations,rule_trace)`, `investment_profile(test_id,version,unit_cost_minor,selling_price_minor,fulfillment_cost_minor,payment_fee_bp,available_budget_minor,target_margin_bp,supplier_moq,lead_time_days,currency,is_current,created_by)`, `investment_recommendation(test_id,investment_profile_id,version,summary,assumptions_snapshot,is_current,created_by)`, `demand_estimate(investment_recommendation_id,low_units,base_units,high_units,assumptions,confidence)`, `unit_economics(investment_recommendation_id,contribution_margin_minor,break_even_units,cac_minor,formulas,is_negative_margin)`, `quantity_scenario(investment_recommendation_id,label,quantity,inventory_cost_minor,expected_units_sold_low,expected_units_sold_high,revenue_low_minor,revenue_high_minor,profit_low_minor,profit_high_minor,sell_through_low,sell_through_high,overstock_risk,stockout_risk,is_feasible,infeasibility_reason)`.
**ACCEPTANCE CRITERIA:**
- `verdict.outcome` CHECK (`go|no_go|extend_test`); `verdict` and `test_result_snapshot` are append-only/immutable.
- `decision_rule_set` UNIQUE **NULLS NOT DISTINCT** `(store_id, category_id, version)`.`
- `test_result_snapshot.data_completeness numeric(5,4)`; `source_metric_snapshot_ids uuid[]`.
- `investment_profile` UNIQUE `(test_id, version)`; `investment_recommendation` UNIQUE `(test_id, version)`; both have `is_current`.
- `demand_estimate.confidence` CHECK (`high|medium|low`); range order low ≤ base ≤ high enforced.
- `quantity_scenario.label` CHECK (`conservative|base|aggressive`); `overstock_risk`/`stockout_risk` CHECK (`low|medium|high`).
- `unit_economics.break_even_units numeric(12,2)`.
- Indexes: `verdict(test_id)`, `test_result_snapshot(test_id, captured_at)`, `investment_recommendation(test_id, version)`.

### DB-0.13 Constraints, foreign keys, and integrity gate
**TASK:** Complete the FK/CHECK pass across all tables: every ERD relationship as a named FK, every spec CHECK named, and no orphan relationships.
**ACCEPTANCE CRITERIA:**
- Every FK exists with intended delete behaviour (`RESTRICT` by default; `CASCADE` only for transient children).
- Circular references resolved by migration order (e.g., `product_concept.source_idea_id`).
- All constraints named (`ck_`, `fk_`, `uq_`).
- An `information_schema` diff against `Specifications.md` returns zero differences.

### DB-0.14 Indexing and performance pass
**TASK:** Add all spec-listed secondary indexes, `pg_trgm` GIN indexes for name search/dedup, and partial indexes for soft-deleted rows.
**ACCEPTANCE CRITERIA:**
- Indexes exist for tenant+status+date access patterns used by list and dashboard endpoints.
- GIN indexes on `product.name` and `product_idea.name`.
- Partial indexes use `WHERE deleted_at IS NULL`.
- `EXPLAIN` on representative queries shows index usage (no seq scan on large tables).
- No redundant or duplicate indexes remain.

### DB-0.15 Row-level security and tenancy enforcement
**TASK:** Enable RLS on every tenant table (including child tables) with a `tenant_isolation` policy comparing `store_id` to `current_setting('app.store_id')::uuid`.
**ACCEPTANCE CRITERIA:**
- RLS enabled on all tenant + child tables (`order_item`, `score_factor`, `import_row`, `import_issue`, `audience_segment`, `post_creative`, `creative_variant`, `ad_set`, `page_version`, `demand_estimate`, `unit_economics`, `quantity_scenario`).
- Tables without direct `store_id` resolve tenancy through their parent FK via documented policy.
- Cross-tenant read returns zero rows; cross-tenant write is rejected.
- Rows with `store_id IS NULL` (platform defaults) are readable by authenticated roles and writable only by the maintenance/owner role.
- Missing `app.store_id` fails closed.

### DB-0.16 Partitioning readiness and retention plan
**TASK:** Prepare `event`, `order`, and `metric_snapshot` for monthly range partitioning and document the purge plan for `import_row`, `import_issue`, and staged `stored_file`.
**ACCEPTANCE CRITERIA:**
- Partitioning plan is documented and tested (monthly on `occurred_at`, `placed_at`, `period_start`).
- If partitioned now, PK includes the partition key and a default partition + monthly creation routine exists.
- If deferred, the exact `ALTER TABLE` plan and PK constraint are documented.
- Retention windows documented per transient table.

### DB-0.17 Concurrency control and optimistic locking
**TASK:** Add `version int NOT NULL DEFAULT 1` to mutable aggregates and enforce optimistic concurrency on update.
**ACCEPTANCE CRITERIA:**
- `version` present on `store`, `user`, `product`, `order`, `product_concept`, `audience_profile`, `landing_page`, `post`, `creative`, `test`, `campaign`, `ad_set`, `ad_variation`, `optimization_recommendation`, `budget_policy`, `investment_profile`, `investment_recommendation`.
- Stale update (`version` mismatch) returns a conflict, never overwrites.
- Append-only/immutable tables carry no `version` and reject mutation.
- `is_current` partial uniques remain authoritative for "one current row" rules.

### DB-0.18 PII classification, encryption, and consent storage
**TASK:** Classify PII columns and protect them: encrypted `order.customer_*`, hash-only IP columns, and persisted consent state.
**ACCEPTANCE CRITERIA:**
- `order.customer_name`, `order.customer_phone`, `order.customer_address_enc` stored encrypted; ciphertext envelope and key rotation documented.
- No raw IP column exists; only `event.ip_hash` and `tracking_session.ip_hash`.
- `feedback_item.text` and `order.customer_*` flagged for restricted role access.
- `tracking_session.consent_state` persisted and queryable for retention decisions.
- PII never appears in plain text in logs or error surfaces.

### DB-0.19 Database roles, privileges, and connection security
**TASK:** Create least-privilege roles (migration/owner, application, read-only reporting, maintenance), pin `search_path`, and require TLS connections.
**ACCEPTANCE CRITERIA:**
- Application role has DML only, cannot run DDL, and cannot bypass RLS.
- Reporting role has `SELECT` only, and no access to base PII tables.
- Maintenance role owns purge/retention jobs only.
- `GRANT`/`REVOKE` statements are idempotent and committed.
- Credentials come from environment/secret store; TLS required; per-role timeouts set.

### DB-0.20 Seeds, fixtures, and migration verification
**TASK:** Create idempotent development seed (demo store, owner/manager/analyst users, taxonomy, default scoring model, default decision rule set, default optimization rule set) and a migration up→down→up verification.
**ACCEPTANCE CRITERIA:**
- Seed runs only outside production and is re-runnable.
- Default platform records exist: `ScoringModel` (`default`, v1), `DecisionRuleSet` (platform default), `OptimizationRuleSet` (`global`).
- CI runs up → down → up cleanly on an empty database.
- Spec parity check passes.

### DB-0.21 CI migration pipeline and rollback drill
**TASK:** Build the CI pipeline `migrate-up → test-schema → test-constraints → test-rls → migrate-down`, plus a rehearsal of recovering from a failed forward migration.
**ACCEPTANCE CRITERIA:**
- Build fails on any migration error, parity diff, constraint test failure, or RLS bypass.
- Migration checksum/lock prevents editing an applied migration.
- Artifacts (generated DDL, parity report, query plans) are attached to the build.
- Restore-from-backup drill is documented and performed once.

### DB-0.22 Performance baseline and query budget validation
**TASK:** Seed a baseline dataset and benchmark representative queries with `EXPLAIN (ANALYZE, BUFFERS)`.
**ACCEPTANCE CRITERIA:**
- Baseline dataset seeded (e.g., 1M events, 100k orders, 50k metric snapshots).
- Benchmarks cover concept list, import history, event-by-type, campaign metrics, verdict lookup, investment history.
- Dashboard-target queries stay under P95 < 2 seconds on the baseline dataset.
- Any query over budget is indexed, rewritten, or escalated with a documented decision.

### DB-0.23 Retention and purge jobs
**TASK:** Implement batched, idempotent purge jobs with documented retention windows per table class.
**ACCEPTANCE CRITERIA:**
- Retention documented: audit ≥ 12 months, events/sessions configurable, transient import staging, staged `stored_file` with no batch.
- Purge respects FK order (issues → rows → batches) and never breaks integrity.
- Soft-deleted rows have a documented hard-delete window.
- Purge runs under the maintenance role and writes an `audit_log` entry (`actor_type = service`).

### DB-0.24 Schema documentation and ERD traceability
**TASK:** Generate schema documentation from `information_schema`/`pg_catalog` with a traceability matrix from each DB task to its spec sections, and diff it in CI.
**ACCEPTANCE CRITERIA:**
- Docs cover every table, column, type, nullability, default, and constraint.
- Each table cross-references its `## Entity Fields` entry and ERD relationship.
- Traceability matrix maps DB tasks → spec sections.
- Undocumented drift fails the build.

---

## Module 0 — Platform Foundations (P0)

### FR-0.1 Store data isolation
- **User Story:** As a merchant, I want my store data isolated so that no other merchant can access or affect it.
- **Acceptance Criteria:**
  - Every domain record carries a `store_id`; all reads and writes are scoped to the authenticated store.
  - Cross-store access returns `403/404` and is logged as a security event.
  - Automated tests cover isolation for imports, concepts, campaigns, events, and metrics.
  - Store deletion follows a documented retention/deletion process.
- **Functional Specifications:**
  - `store_id uuid NOT NULL` on every tenant-owned table (per spec tenancy convention).
  - `ITenantContext` supplies `storeId`, `userId`, `role` from request middleware.
  - `IRowLevelSecurity.applyFilter<T>(query, storeId)` applied in every repository.
  - PostgreSQL row-level security policies on tenant tables, including child tables (`OrderItem`, `ScoreFactor`, `ImportRow`).
- **Notes:** Foundation for every other module. No schema rewrite needed for future multi-store (add `Membership` later).

### FR-0.2 Roles and spend approval
- **User Story:** As a store owner, I want to control who can publish pages, launch campaigns, and approve spend.
- **Acceptance Criteria:**
  - A documented permission matrix exists for Owner, Manager, and Analyst roles.
  - Only Owner/Manager can publish pages, submit campaigns, or approve budget changes.
  - Every privileged action is attributed to a user.
  - Unauthorized attempts are blocked with a clear message.
- **Functional Specifications:**
  - `User.role text` — `owner | manager | analyst`.
  - `IAuthorizationService.checkPermission(storeId, userId, action)` returns `PermissionResult`.
  - Server-side permission check on every privileged endpoint and use case.
- **Notes:** Matrix must be written into the spec before build starts.

### FR-0.3 Audit trail
- **User Story:** As an owner, I want an immutable record of consequential actions so I can investigate changes.
- **Acceptance Criteria:**
  - Logs capture actor, store, action, target, UTC timestamp, and before/after values for import commits, publications, budget changes, verdicts, and optimization actions.
  - Logs are append-only and retained for a configurable period (default ≥12 months).
  - Owner can filter and export by date, user, and target.
  - Log entries cannot be edited through the UI or API.
- **Functional Specifications:**
  - `AuditLog` entity: `actor_user_id`, `actor_type` (`user | system | service`), `action`, `target_type`, `target_id`, `before jsonb`, `after jsonb`, `metadata jsonb`, `ip_hash char(64)`, `correlation_id uuid`.
  - `IAuditService.log(action, targetType, targetId, before, after, meta: AuditMeta)`.
  - Append-only enforcement: `created_at` only, no `updated_at`, no update/delete path in API or UI.
- **Notes:** `AuditMeta` value object carries `actorUserId`, `actorType`, `correlationId`, `ipHash`.

### FR-0.4 Async jobs, idempotency, and status
- **User Story:** As a merchant, I want long-running operations to be reliable and not create duplicates when I retry.
- **Acceptance Criteria:**
  - Imports, page generation, ad publication, and metric sync run as background jobs with states: queued, running, succeeded, failed, partial.
  - Retrying with the same idempotency key does not duplicate records or campaigns.
  - Failures expose a human-readable reason plus a job/correlation ID.
  - UI shows last-updated time and offers a safe manual retry.
- **Functional Specifications:**
  - `AsyncJob` entity: `job_type`, `state`, `idempotency_key` (unique where not null), `payload`, `result`, `progress_current/total`, `attempt_count`, `max_attempts`, `error_code`, `error_message`, `correlation_id`, timing columns.
  - `IJobQueue.enqueue(jobType, payload, idempotencyKey, correlationId)` and `IJobProcessor<T>.process(job)`.
  - `IdempotencyService.check(key)` / `.store(key, response, ttl)` over `IIdempotencyStore`.
  - `CorrelationService.getCorrelationId()` / `.setCorrelationId(id)` for end-to-end traceability.
- **Notes:** DB-backed queue is sufficient for MVP; Redis later without changing interfaces.

### FR-0.5 AI/model governance and degraded mode
- **User Story:** As a platform operator, I want AI outputs to be versioned and safely degradable so the product remains trustworthy.
- **Acceptance Criteria:**
  - Each AI output or score stores model/prompt/template version, input snapshot reference, and timestamp.
  - Merchant data is not used to train shared models without explicit opt-in.
  - If an AI or ad-platform dependency is unavailable, the flow degrades gracefully with a clear message, retry option, and manual fallback.
  - AI-generated content is labeled as such in the UI; the system never fabricates evidence or results.
- **Functional Specifications:**
  - Version fields on `GenerationRun.model_version`, `Evaluation.model_version`, `PageVersion.model_version`, `Creative.model_version`, `ProductIdea.model_version`.
  - `input_snapshot jsonb` on every generated artifact for reproducibility.
  - Dependency failure paths on copy generation, page generation, scoring, and ad publication with explicit degraded-mode messaging.
  - UI label on AI-generated copy and creative assets.
- **Notes:** Cross-cutting; enforce during every AI-backed task, not as a separate feature.

## Module 1.1 — Historical Store Data Import (P0)

### FR-1.1.1 CSV upload and format validation (+ file limits)
- **User Story:** As a merchant, I want to upload a CSV of my historical sales so that I can reuse existing data without manual entry.
- **Acceptance Criteria:**
  - Accepts `.csv` up to a configured limit (e.g., 20 MB) with a downloadable template.
  - Rejects unsupported type, encoding, or empty files with a specific error.
  - Uploaded files are staged only; no sales records are written at this step.
  - Success or failure is reported unambiguously.
- **Functional Specifications:**
  - `IImportService.uploadCsv(storeId, file: Stream)` → `StoredFile` with `purpose = sales_csv`, `status = staged`.
  - `StoredFile` fields: `original_filename`, `mime_type`, `size_bytes`, `checksum_sha256`, `storage_provider`, `storage_key`.
  - `IFileStorage.upload(stream, filename, contentType)` for the binary payload.
  - Validation of extension, MIME type, size ceiling, encoding, and emptiness before accepting.
- **Notes:** Staged file is purged by a retention job if no batch is created.

### FR-1.1.2 Column mapping
- **User Story:** As a merchant, I want to map my columns to the required fields so my records are interpreted correctly.
- **Acceptance Criteria:**
  - Required fields: `product_id`, `product_name`, `order_date`, `quantity`, `sales_amount`; optional: `order_id`, `currency`, `sku`.
  - System auto-suggests mappings; merchant can override; one source column maps to one target field.
  - Sample values are shown per column.
  - Import cannot proceed while a required field is unmapped.
  - Mapping is saved per store for reuse.
- **Functional Specifications:**
  - `ColumnMapping` entity: `name`, `source_type`, `mapping jsonb` (`{ target_field: source_column }`), `is_default`, `created_by`.
  - `IImportService.suggestMapping(batchId)` → `MappingSuggestion`; `applyMapping(batchId, mappingId)` persists the choice.
  - Header-name heuristic scoring for auto-suggestion; merchant override always wins.
  - One-to-one source/target constraint enforced server-side.
- **Notes:** Sample values come from the staged rows; keep 3 samples per column.

### FR-1.1.3 Row validation and duplicate detection
- **User Story:** As a merchant, I want invalid rows identified before import so I can fix them.
- **Acceptance Criteria:**
  - Validates required values, date parsing (store timezone), integer quantity > 0, numeric amount ≥ 0, valid currency, and product consistency.
  - Duplicate rules are explicit: same `order_id` + `product_id`, or same product/date/quantity/amount when no order ID exists.
  - Duplicates are detected both within the file and against existing records.
  - Errors return row number, field, reason, and raw value.
  - The merchant explicitly chooses strict (all-or-nothing) or lenient (skip invalid rows) mode.
- **Functional Specifications:**
  - `ImportRow` (staged, transient): `import_batch_id`, `row_number`, `raw_data jsonb`, `normalized_data jsonb`, `status` (`valid | invalid | duplicate | imported | skipped`), `issue_count`.
  - `ImportIssue`: `import_batch_id`, `import_row_id`, `row_number`, `field_name`, `issue_code`, `severity`, `message`, `raw_value`.
  - `IImportService.validate(batchId)` → `ValidationResult`.
  - `ImportBatch.strict_mode boolean` selects all-or-nothing vs skip-invalid behaviour.
  - Deduplication key: `order_id + product_id` when present, else hash of `product + date + quantity + amount`; compare against `Order.dedupe_hash` and within-file hashes.
  - Date parsing uses `Store.timezone`; quantity must be integer > 0; amount numeric ≥ 0; currency must be a known ISO 4217 code.
- **Notes:** Validation must run as a background job for large files; staged rows are purgeable.

### FR-1.1.4 Preview and error review before commit
- **User Story:** As a merchant, I want to review imported records and errors before saving so I can verify accuracy.
- **Acceptance Criteria:**
  - Displays a sample of valid rows plus all errors (paginated or downloadable as an error report).
  - Displays counts: total, valid, invalid, duplicates.
  - Nothing is persisted before explicit confirmation.
  - Cancel leaves the database unchanged.
- **Functional Specifications:**
  - `IImportService.preview(batchId, limit, offset)` → `PreviewResult` with row samples and counts.
  - `IImportService.downloadErrorReport(batchId)` → `Stream`; report written to `StoredFile` and linked via `ImportBatch.error_report_file_id`.
  - `ImportBatch` counts: `total_rows`, `valid_rows`, `invalid_rows`, `duplicate_rows`, `imported_rows`, `skipped_rows`.
  - Cancel sets `ImportBatch.status = cancelled` and deletes staged `ImportRow`/`ImportIssue` rows only.
- **Notes:** Preview is strictly read-only against domain tables.

### FR-1.1.5 Commit and import summary
- **User Story:** As a merchant, I want a clear summary after import so I know exactly what was accepted.
- **Acceptance Criteria:**
  - Commit is transactional; accepted rows are written with an `import_id`.
  - Summary shows imported, skipped, rejected, duplicates, duration, and date range.
  - Import history is viewable and the error report is re-downloadable.
  - Re-uploading the same file warns about duplicates and respects idempotency.
  - The update policy for existing records is explicit; no silent overwrite.
- **Functional Specifications:**
  - `IImportService.commit(batchId)` → `ImportSummary`.
  - Write `Product` (upsert by `external_product_id`/`sku` within store), `Order` (`origin = imported`, `import_batch_id`, `placed_at`, `imported_at`, `dedupe_hash`), and `OrderItem` lines.
  - Rows sharing `external_order_id` group into one `Order` with multiple `OrderItem` rows; rows without order ID create one `Order` each.
  - `ImportBatch.status = completed`, `completed_at` set; `started_at` gives duration.
  - Transaction boundary via `IUnitOfWork`; failure leaves database unchanged and marks batch `failed`.
  - Idempotency key derived from file checksum + store; repeated commit returns the original summary instead of re-inserting.
  - `IImportService.getImportHistory(storeId, filters)` for the history list.
- **Notes:** Update policy (skip / update / reject-existing) must be an explicit merchant choice at commit time.

### FR-1.1.6 E-commerce integration connect and historical import
- **User Story:** As a merchant, I want to connect my store so I can import historical data without exporting it manually.
- **Acceptance Criteria:**
  - Supported platform connects via OAuth/API key with read-only catalog and order scopes.
  - Credentials are encrypted at rest; disconnect revokes access and stops syncing.
  - Merchant selects a date range; products and orders map to the canonical schema.
  - Progress and per-entity results are displayed; partial failures list reasons and support safe retry.
  - Imported records are deduplicated against CSV imports.
- **Functional Specifications:**
  - `StoreConnection` entity: `provider`, `external_store_id`, `status`, `scopes text[]`, `access_token_encrypted`, `refresh_token_encrypted`, `token_expires_at`, `last_synced_at`; unique per `(store_id, provider)`.
  - Integration adapter per provider (e.g., Shopify, WooCommerce) behind a shared interface; maps to `Product`/`Order`/`OrderItem` canonical shape.
  - Sync runs as `AsyncJob` (`job_type = integration_sync`) with progress and per-entity results.
  - Same `dedupe_hash` and `external_product_id`/`external_order_id` uniqueness as the CSV path.
  - Disconnect sets `status = revoked`, clears tokens, revokes upstream grant.
- **Notes:** Depends on decision D1 (platform scope) and D2 (payment-related fields). Read-only scopes only for MVP.

## Module 1.2 — Customer Preference and Audience Profiling (P0)

### FR-1.2.1 Product category and niche
- **User Story:** As a store manager, I want to select my category and niche so recommendations match my business.
- **Acceptance Criteria:**
  - Merchant can select one or more categories from a taxonomy.
  - Merchant can add a custom niche within a defined length limit.
  - At least one category is required.
  - Selection is saved to the store profile.
- **Functional Specifications:**
  - `Category` entity (global taxonomy): `parent_id`, `name`, `slug`, `is_active`, `sort_order`.
  - `Niche` entity: `category_id`, `store_id` (null = global curated), `name`, `slug`, `is_active`; partial unique on `(store_id, slug)`.
  - Store profile references selected category/niche IDs; validation requires ≥1 category.
  - Custom niche name length limit enforced server-side.
- **Notes:** Seed the global taxonomy before onboarding is usable.

### FR-1.2.2 Target customer profile
- **User Story:** As a store manager, I want to define my target audience so evaluations reflect my intended customers.
- **Acceptance Criteria:**
  - Captures target location(s), age range, interests, and preferred language(s).
  - Age range rejects inverted or out-of-bounds values.
  - Multiple audience segments are supported.
  - Optional fields may be left empty.
  - Saved profile is editable.
- **Functional Specifications:**
  - `AudienceProfile` entity: `version`, `status`, `is_current`, `niche_ids uuid[]`, `languages text[]`, `notes`, `created_by`.
  - `AudienceSegment`: `audience_profile_id`, `label`, `locations jsonb`, `age_min`, `age_max`, `genders text[]`, `interests text[]`, `languages text[]`.
  - `CHECK (age_min <= age_max)` plus server-side bounds validation.
  - `IAudienceService.upsertProfile(storeId, dto)` / `upsertSegment(profileId, dto)`.
- **Notes:** Location values validated against the `Country` reference table.

### FR-1.2.3 Customer feedback intake
- **User Story:** As a store manager, I want to submit customer feedback so recommendations account for stated needs.
- **Acceptance Criteria:**
  - Accepts manual text entry or a supported file (`.csv`, `.txt`, `.xlsx`), with type/size/encoding validation.
  - Each feedback item is timestamped and linked to the correct store.
  - Rejected input returns a specific reason.
  - PII handling and consent are documented where feedback may contain personal data.
- **Functional Specifications:**
  - `FeedbackItem` entity: `audience_profile_id`, `source` (`manual | file`), `stored_file_id`, `text`, `language`, `sentiment`, `captured_at`.
  - `IAudienceService.submitFeedback(storeId, dto)` and `uploadFeedbackFile(storeId, file)`.
  - `StoredFile.purpose = feedback_file`; type/size/encoding validation mirroring CSV rules.
  - Rejection reasons surfaced per file/field without echoing PII.
- **Notes:** Feedback text may contain PII — document consent and retention handling before launch.

### FR-1.2.4 Save, version, and consume audience profile
- **User Story:** As a store manager, I want profile updates to apply predictably to future evaluations.
- **Acceptance Criteria:**
  - Each save creates a new profile version.
  - Evaluations record which profile version was used.
  - Editing the profile does not retroactively change past evaluations.
  - Version history is viewable.
- **Functional Specifications:**
  - `AudienceProfile.version int` with unique `(store_id, version)` and partial unique `(store_id)` where `is_current`.
  - On save: increment version, set new row `is_current = true`, demote prior row.
  - `Evaluation.input_snapshot jsonb` records the profile version and segment data used.
  - `IAudienceService.getProfileHistory(storeId)` returns all versions.
- **Notes:** Profiles are immutable once referenced by an evaluation.

## Module 2.1 — Proprietary Product Assessment and Scoring (P0)

### FR-2.1.1 Create a product concept with validation
- **User Story:** As a brand owner, I want to enter my product details so the platform can evaluate the concept.
- **Acceptance Criteria:**
  - Captures name, description, category, proposed price, estimated cost, currency, and optional image.
  - Required-field and image type/size validation are enforced inline.
  - Gross margin is computed and displayed.
  - Concepts can be saved as drafts and belong to one store.
- **Functional Specifications:**
  - `ProductConcept` entity: `name`, `description`, `category_id`, `niche_id`, `price_minor`, `cost_minor`, `currency`, `gross_margin_bp`, `image_file_id`, `status = draft`, `version`, `created_by`.
  - `Money` value object for money handling (minor units + ISO currency).
  - `gross_margin_bp` computed from price and cost on save; negative margin flagged.
  - Image upload to `StoredFile` (`purpose = product_image`) with type/size validation.
- **Notes:** `ProductConcept` is separate from `Product` (canonical catalogue product); no silent coupling.

### FR-2.1.2 Manage multiple concepts and lifecycle
- **User Story:** As a brand owner, I want to submit and manage multiple concepts so I can prioritize a portfolio.
- **Acceptance Criteria:**
  - Merchant can list, create, edit, archive, and search concepts.
  - States are explicit: draft, evaluated, selected, archived.
  - Evaluated concepts cannot be hard-deleted.
  - List is sortable by score, category, and date.
- **Functional Specifications:**
  - `ProductConcept.status text` — `draft | evaluated | selected | archived`; `deleted_at` soft delete.
  - Repository filters for status, category, date range; sort keys `score` (latest evaluation), `category`, `created_at`.
  - Hard delete rejected when an `Evaluation` exists for the concept.
  - `ProductConcept.version int` for optimistic concurrency on edits.
- **Notes:** State transitions are explicit; archive is reversible, hard delete is not.

### FR-2.1.3 Data sufficiency assessment
- **User Story:** As a brand owner, I want to know whether there is enough data before trusting a score.
- **Acceptance Criteria:**
  - Checks sales history volume/period, audience completeness, price/cost, and optional competitive data.
  - Returns per-input status: available, missing, stale, insufficient.
  - Missing critical inputs block scoring or flag it as low-confidence per policy.
  - The system never silently imputes critical missing inputs.
- **Functional Specifications:**
  - `SufficiencyCheck` entity: `product_concept_id`, `sales_history_status`, `audience_status`, `cost_price_status`, `competitive_data_status`, `overall_status`, `blocking_reasons jsonb`, `checked_at`.
  - `IEvaluationService.runSufficiencyCheck(conceptId)` → `SufficiencyCheck`.
  - Each per-input status from `available | missing | stale | insufficient`; staleness window per input type.
  - `blocking_reasons` names the exact missing input; no default substitution.
- **Notes:** Sales history volume/period thresholds must be documented before build.

### FR-2.1.4 Viability scoring
- **User Story:** As a brand owner, I want a viability score so I can prioritize before paying for tests.
- **Acceptance Criteria:**
  - Produces a score on a documented scale using a versioned, documented model.
  - Same inputs and model version produce the same score.
  - Inputs, weights, and model version are recorded with each score.
  - Score is reported as unavailable (not zero) when critical inputs are missing.
  - Batch evaluation of multiple concepts is supported.
- **Functional Specifications:**
  - `ScoringModel` entity: `key`, `version`, `name`, `description`, `weights jsonb`, `parameters jsonb`, `is_active`, `effective_from`; unique `(key, version)`.
  - `Evaluation` entity: `scoring_model_id`, `model_version`, `score numeric(7,4)` (null when unavailable), `score_scale`, `confidence`, `is_reliable`, `sufficiency_check_id`, `input_snapshot jsonb`, `evaluated_at`.
  - `IScoringStrategy.score(concept, inputs, model)` → `EvaluationResult`; rules-based weighted implementation for v1.
  - `IEvaluationService.evaluate(conceptId, modelId?)` and `batchEvaluate(storeId, conceptIds)` (runs as an async job).
  - Determinism guaranteed: same `input_snapshot` + model version → identical score.
- **Notes:** Decision D6 — rules-based v1 for explainability and reproducibility.

### FR-2.1.5 Score explanation and limitations
- **User Story:** As a brand owner, I want to understand what drives a score so I can judge its reliability.
- **Acceptance Criteria:**
  - Displays the top positive and negative contributing factors with contribution values.
  - Displays confidence and limitations (missing competitive data, small sample, stale history).
  - Distinguishes measured inputs from inferred values.
  - Makes no guarantee-of-sales claims.
- **Functional Specifications:**
  - `ScoreFactor` entity: `evaluation_id`, `factor_key`, `factor_label`, `direction` (`positive | negative | neutral`), `contribution numeric(7,4)`, `explanation`, `evidence jsonb`.
  - `Evaluation.confidence` (`high | medium | low`) and `is_reliable` derived from the sufficiency check.
  - UI renders top contributors ranked by absolute contribution, with measured vs inferred labeling from `evidence`.
  - Copy guardrails: no guarantee-of-sales wording in any score surface.
- **Notes:** Limitations list is derived from the matching `SufficiencyCheck`.

### FR-2.1.6 Compare, sort, and select concepts
- **User Story:** As a brand owner, I want to compare scores so I can choose which concepts to test first.
- **Acceptance Criteria:**
  - Side-by-side comparison of evaluated concepts with score and key metrics.
  - Sorting and filtering by score, category, and date.
  - Merchant can select one or more concepts to advance to Stage 2.
  - Selection is recorded and visible in the concept state.
- **Functional Specifications:**
  - `IEvaluationService.compare(conceptIds)` → `ComparisonResult` with score, confidence, key factors per concept.
  - `ProductConcept.status` transition to `selected`, recorded with actor and timestamp via audit.
  - Filter/sort API on the concept list endpoint.
- **Notes:** Selection is the handoff into Stage 2 (landing page / campaign setup).

## Module 2.2 — Automated Product Recommendation Engine (P0)

### FR-2.2.1 Generate recommendations
- **User Story:** As a merchant, I want product ideas based on my niche and audience so I can find expansion opportunities.
- **Acceptance Criteria:**
  - On-demand generation uses niche, audience profile, sales history, and trend/competitive data when available.
  - Returns a configurable number of ideas.
  - Deduplicates against existing concepts and previously dismissed ideas.
  - Generation metadata (inputs, model version, timestamp) is stored.
- **Functional Specifications:**
  - `IRecommendationService.generate(storeId, requestedBy, count)` → `GenerationRun`; runs as async job (`job_type = recommendation_generation`).
  - `GenerationRun` entity: `requested_by`, `model_version`, `input_snapshot jsonb`, `requested_count`, `returned_count`, `status`, `error_message`, timings.
  - `ProductIdea` entity: `generation_run_id`, `name`, `description`, `category_id`, `niche_id`, `rationale`, `state`, `dismissed_reason`, `converted_concept_id`, `model_version`.
  - Deduplication: fuzzy/normalized name+description match against `ProductConcept` and dismissed `ProductIdea`.
  - `IRecommendationService.getIdeas(storeId, filters)` for the library list.
- **Notes:** Depends on decision D3 (competitive data source); degrade gracefully when unavailable.

### FR-2.2.2 Rationale and evidence provenance
- **User Story:** As a merchant, I want to understand why an idea is recommended so I can judge relevance.
- **Acceptance Criteria:**
  - Each idea includes a description, rationale, and evidence list.
  - Every evidence item is labeled **Verified** (source, date, link) or **AI Hypothesis**.
  - No fabricated sources or links are displayed.
  - Stale evidence is flagged.
  - Verified and hypothesized evidence are visually distinct.
- **Functional Specifications:**
  - `IdeaEvidence` entity: `product_idea_id`, `evidence_type` (`verified | hypothesis`), `claim`, `source_name`, `source_url`, `source_published_at`, `retrieved_at`, `confidence`.
  - `CHECK (evidence_type = 'verified' requires source_url)` at database level.
  - Staleness flag when `source_published_at` exceeds the configured freshness window.
  - UI renders verified vs hypothesis with distinct treatment; no link rendered without a stored source.
- **Notes:** No fabricated sources — the UI must never synthesize a link from model output.

### FR-2.2.3 Save or dismiss ideas
- **User Story:** As a merchant, I want to save or dismiss ideas so my library stays relevant.
- **Acceptance Criteria:**
  - Merchant can save an idea to the library or dismiss it with an optional reason.
  - Dismissed ideas are not re-suggested unless restored.
  - State persists per store and per user.
- **Functional Specifications:**
  - `ProductIdea.state text` — `new | saved | dismissed | converted`; `dismissed_reason` optional.
  - `IRecommendationService.save(ideaId)` and `.dismiss(ideaId, reason?)`.
  - Dismissed ideas excluded from generation dedup candidates until explicitly restored.
- **Notes:** Dismissal is per store (MVP is one store per user), with user attribution retained in audit.

### FR-2.2.4 Convert an idea into a product concept
- **User Story:** As a merchant, I want to turn an idea into a concept so I can evaluate it.
- **Acceptance Criteria:**
  - Conversion prefills an editable concept with the idea's details.
  - Concept links back to its source idea; source is marked as converted.
  - Merchant must confirm conversion.
  - Converted concept enters the FR-2.1 evaluation flow.
- **Functional Specifications:**
  - `IRecommendationService.convertToConcept(ideaId)` → `ProductConcept` with `source_idea_id` set and `status = draft`.
  - Pre-fill from `ProductIdea` (name, description, category, niche) — price/cost remain merchant inputs.
  - Update `ProductIdea.state = converted` and set `converted_concept_id` in the same transaction.
  - Confirmation step in the UI before persisting.
- **Notes:** Traceability both directions (`ProductConcept.source_idea_id` ↔ `ProductIdea.converted_concept_id`).

## Module 3.1 — Automated Micro-Landing Page Builder (P0)

### FR-3.1.1 Product input and page options
- **User Story:** As an e-commerce seller, I want to enter product details and options so a page can be generated.
- **Acceptance Criteria:**
  - Captures image (JPG/PNG/WebP with type and size limits), name, description, price, currency, language, target market, and order method.
  - Mandatory fields are validated before generation.
  - Draft input is autosaved.
  - Order method options are WhatsApp or COD.
- **Functional Specifications:**
  - `LandingPage` entity: `product_concept_id`, `test_id`, `slug` (unique), `status = draft`, `template_id`, `current_version_id`, `order_channel_id`, `language`, `currency`, `published_url`, `published_at`.
  - `PageVersion` entity holds the mutable draft content (`content jsonb`, `price_minor`, `currency`, `image_file_ids`, `generated_by`, `model_version`).
  - Image upload to `StoredFile` (`purpose = product_image`) with JPG/PNG/WebP and size validation.
  - Autosave persists `PageVersion` on a debounce; `version int` increments per save with unique `(landing_page_id, version)`.
  - Order method limited to WhatsApp or COD via `OrderChannel`.
- **Notes:** Language drives copy generation and RTL layout; target market drives phone/address validation.

### FR-3.1.2 Generate a responsive landing page
- **User Story:** As an e-commerce seller, I want a generated page so I do not have to build one manually.
- **Acceptance Criteria:**
  - Uses a predefined responsive template containing image, name, description, price, and CTA.
  - Renders correctly on mobile and desktop breakpoints.
  - Generation completes within 5 minutes at P95 under stated supported conditions.
  - Failures are reported with a reason and are retryable.
- **Functional Specifications:**
  - `PageTemplate` entity: `key`, `version`, `name`, `is_active`, `schema jsonb`; unique `(key, version)`.
  - `ILandingPageService.create(storeId, conceptId, testId, templateId)` starts `job_type = page_generation`.
  - Generated output written as a new `PageVersion` with `generated_by = ai` and `model_version` set.
  - Responsive rendering at mobile and desktop breakpoints from the template schema.
  - Failure path stores `AsyncJob.error_code` / `error_message` and offers a safe retry.
- **Notes:** Performance budget: P95 ≤ 5 minutes for generation.

### FR-3.1.3 Product copy generation and editing
- **User Story:** As an e-commerce seller, I want copy in my market's language so the page fits my audience.
- **Acceptance Criteria:**
  - Generates copy in the selected language and market, including RTL layout where applicable.
  - Merchant can regenerate and edit all copy.
  - Generated copy avoids unverifiable medical, absolute, or guaranteed claims.
  - Edits persist in the draft.
- **Functional Specifications:**
  - `ILandingPageService.generateCopy(pageId)` → `CopySuggestion`, applied to the current draft `PageVersion`.
  - Language selection from the `Language` reference table, including `direction` (`ltr | rtl`); RTL layout applied when direction is `rtl`.
  - Claim filter rejecting medical, absolute, and guaranteed-outcome phrasing before the copy is stored.
  - Merchant edits stored in `PageVersion.content jsonb` and persisted in the draft.
  - Regeneration is allowed and does not overwrite manual edits without explicit confirmation.
- **Notes:** Decision D8 (markets, currencies, RTL) constrains the supported set for v1.

### FR-3.1.4 Ordering mechanism
- **User Story:** As an e-commerce seller, I want WhatsApp or COD ordering so customers can order in the way they expect.
- **Acceptance Criteria:**
  - WhatsApp option produces a `wa.me` deep link with a prefilled message and attribution token.
  - COD option renders a form with required fields.
  - Selected mechanism appears on the published page.
  - Link or form is verified working before publish.
- **Functional Specifications:**
  - `OrderChannel` entity: `landing_page_id` XOR `post_id`, `type` (`whatsapp | cod`), `whatsapp_number`, `whatsapp_message_template`, `cod_form_schema jsonb`, `is_active`.
  - `CHECK` constraints per spec: WhatsApp requires `whatsapp_number`, COD requires `cod_form_schema`; exactly one of page/post.
  - WhatsApp URL: `https://wa.me/{number}?text={encoded message with tracking token}`.
  - `ILandingPageService.configureOrderChannel(pageId, dto)`; pre-publish verification of link and required form fields.
- **Notes:** Attribution token comes from `TrackingLink` so WhatsApp clicks can be attributed.

### FR-3.1.5 Preview, edit, publish, and shareable URL
- **User Story:** As an e-commerce seller, I want to review and publish my page so I keep control of presentation.
- **Acceptance Criteria:**
  - Preview is available in desktop and mobile views.
  - Merchant can edit supported text and product details.
  - Publish requires explicit confirmation and valid mandatory fields.
  - Successful publish returns a live HTTPS URL.
  - Published pages can be updated or unpublished; an unpublished URL stops serving or shows an unavailable state.
  - Generated pages meet a baseline accessibility check (alt text, labels, contrast).
- **Functional Specifications:**
  - `ILandingPageService.preview(pageId, versionId?)`, `.updateDraft(pageId, updates)`, `.publish(pageId)`, `.unpublish(pageId)`.
  - Publish: validates mandatory fields, freezes the current draft into `published_version_id`, sets `status = published`, `published_at`, `published_url`; publish is audited.
  - Unpublish sets `status = unpublished`; the public route returns an unavailable state instead of the content.
  - Updates to a published page create a new `PageVersion` and republish.
  - Accessibility baseline: alt text present on images, labels on form fields, contrast check on the template palette.
- **Notes:** WCAG 2.1 AA baseline for generated pages; accessibility check must run pre-publish.

## Module 3.2 — Dynamic Social Ad Creative and Campaign Setup (P0)

### FR-3.2.1 Generate ad copy variations
- **User Story:** As a digital marketer, I want multiple ad copy variations so I can test different messages.
- **Acceptance Criteria:**
  - Generates a configurable number of distinct variations (default 3–5) from product and landing-page data.
  - Respects platform character limits and the campaign language.
  - Each variation is linked to the correct product.
  - Near-duplicate variations are flagged.
- **Functional Specifications:**
  - `ICampaignService.generateVariations(dto)` → `List<AdVariation>`.
  - `AdVariation` entity: `adset_id`, `name`, `copy_text`, `headline`, `description`, `creative_file_id`, `primary_creative_id`, `post_id`, `destination_url`, `status = draft`.
  - Platform character-limit table per provider and field; generation truncates/validates against it.
  - Near-duplicate detection by normalized text similarity → flagged for review.
  - Variations inherit the campaign language and link to the ad set's product/page.
- **Notes:** Copy generation reuses the same claim filter as landing-page copy.

### FR-3.2.2 Review, edit, approve, or discard variations
- **User Story:** As a digital marketer, I want to curate variations so only approved messages run.
- **Acceptance Criteria:**
  - Each variation can be edited, approved, or discarded.
  - Status is visible for every variation.
  - Only approved variations are eligible for publication.
  - At least one approved variation is required to proceed.
- **Functional Specifications:**
  - `AdVariation.status text` — `draft | approved | discarded | submitted | active | paused | rejected | failed`; `rejection_reason` for platform rejections.
  - `ICampaignService.updateAdVariation(id, updates)`, `.approveVariation(id)`, `.discardVariation(id)`.
  - Publication eligibility filter: `status = approved`.
  - Pre-flight blocks submission when the approved count is zero.
- **Notes:** Approval actions are audited with the approving user.

### FR-3.2.3 Campaign configuration
- **User Story:** As a digital marketer, I want to configure platform, audience, budget, and duration so the test has defined parameters.
- **Acceptance Criteria:**
  - Captures platform, objective, audience (location/age/interests or saved audience), budget, currency, and start/end or duration.
  - Validates minimum budget, valid dates, and required fields.
  - Configuration is saved as a draft before submission.
- **Functional Specifications:**
  - `Campaign` entity: `test_id`, `provider`, `name`, `objective`, `status = draft`, `budget_type`, `budget_minor`, `currency`, `start_at`, `end_at`, `created_by`.
  - `AdSet` entity: `campaign_id`, `name`, `status`, `targeting jsonb`, `budget_type`, `budget_minor`, `currency`, `start_at`, `end_at`.
  - `ICampaignService.createCampaign(storeId, dto)` and `.createAdSet(campaignId, dto)`.
  - Validation: platform from `AdPlatform` reference table, minimum budget per platform, `start_at < end_at`, targeting references valid locations/ages.
  - Targeting may reuse the current `AudienceProfile`/`AudienceSegment` as the saved audience.
- **Notes:** Targeting JSONB requires a `schema_version` key per the scalability notes.

### FR-3.2.4 Campaign association and tracking parameters
- **User Story:** As a digital marketer, I want the campaign linked to its product and page so results are attributable.
- **Acceptance Criteria:**
  - Campaign links to exactly one product and one landing page.
  - UTM/click parameters are generated and embedded in the ad destination.
  - Association is visible on the campaign detail screen.
  - Missing or invalid tracking parameters block publication.
- **Functional Specifications:**
  - `TrackingLink` entity: `test_id`, `campaign_id`, `adset_id`, `ad_variation_id`, `landing_page_id` XOR `post_id`, `token` (unique), `utm_source/medium/campaign/content/term`, `destination_url`.
  - `ICampaignService.generateTrackingLink(dto)` → `TrackingLink`.
  - `AdVariation.destination_url` populated with the generated tracking URL.
  - Publication blocked when `destination_url` is missing or lacks valid tracking parameters.
- **Notes:** `AdVariation` CHECK requires `post_id` or `destination_url`.

### FR-3.2.5 Validation and preview before submission
- **User Story:** As a digital marketer, I want a pre-flight check so I do not submit an invalid campaign.
- **Acceptance Criteria:**
  - Pre-flight verifies connected account, approved creative, valid budget, live landing page, and tracking parameters.
  - Ad preview is displayed.
  - Submission is blocked with a specific list of unresolved items.
- **Functional Specifications:**
  - `ICampaignService.validate(campaignId)` → `ValidationResult` with an itemised unresolved list.
  - Checks: `AdAccountConnection.status = connected` and token not expired, ≥1 approved `AdVariation`, budget within minimum, `LandingPage.status = published`, `TrackingLink` present and valid.
  - Ad preview renders copy, creative, and destination URL for each approved variation.
- **Notes:** The same validation list is shown pre-publish and pre-submit.

### FR-3.2.6 Advertising account authorization
- **User Story:** As a digital marketer, I want to connect an ad account so the platform can publish campaigns.
- **Acceptance Criteria:**
  - OAuth connection to each supported platform with minimal scopes.
  - Tokens are encrypted and refreshed; disconnect is supported.
  - Connection status and account identity are displayed.
  - Expired or revoked authorization is surfaced before submission.
- **Functional Specifications:**
  - `AdAccountConnection` entity: `provider`, `external_account_id`, `account_name`, `status`, `scopes text[]`, `access_token_encrypted`, `refresh_token_encrypted`, `token_expires_at`, `last_synced_at`, `metadata`; unique `(store_id, provider, external_account_id)`.
  - `ICampaignService.authorizeAccount(storeId, provider)` → `AuthUrl`; `.completeAccountAuth(storeId, provider, code, state)` → `AdAccountConnection`.
  - `IAdPlatformClient.refreshToken(creds)` for token renewal; encryption at rest for all token fields.
  - Disconnect sets `status = revoked` and stops sync; expired/revoked states surface in pre-flight.
- **Notes:** Decision D1 sets the platform set for MVP; implement the interface so more platforms can be added without changes.

### FR-3.2.7 Publish campaign and report status
- **User Story:** As a digital marketer, I want to publish an approved campaign and see the result so I can launch without manual recreation.
- **Acceptance Criteria:**
  - Publication requires explicit merchant approval.
  - Submission is idempotent and returns the platform campaign ID.
  - Status states include submitted, active, rejected, failed, and paused.
  - Platform API errors are mapped to actionable messages.
  - Retry does not create duplicate campaigns.
- **Functional Specifications:**
  - `ICampaignService.publish(campaignId, approvedBy)` → `PublicationAttempt`.
  - `PublicationAttempt` entity: `campaign_id` XOR `adset_id` XOR `ad_variation_id`, `provider`, `attempt_number`, `status`, `external_id`, redacted `request_payload`, `response_payload`, `error_code`, `error_message`, `submitted_by`, `submitted_at`.
  - `IAdPlatformClient.publishCampaign/publishAdSet/publishAd(req)` → `PublishResult`.
  - `Campaign.external_campaign_id` / `AdSet.external_adset_id` / `AdVariation.external_ad_id` written on success.
  - Idempotency key per campaign publish; retry reuses the existing attempt.
  - Platform error mapping table → actionable merchant-facing messages; raw payloads stored redacted.
- **Notes:** Explicit merchant approval (Owner/Manager) required per FR-0.2.

## Module 4.1 — Behavioral Tracking and Regional Conversion Intent (P0)

### FR-4.1.1 Event model and ingestion
- **User Story:** As a merchant, I want consistent event tracking so I can compare intent signals reliably.
- **Acceptance Criteria:**
  - Canonical events: `page_view`, `product_view`, `cta_click`, `whatsapp_click`, `cod_form_start`, `cod_order_submitted`, `deposit_confirmed`.
  - Each event has `event_id`, `store_id`, `product_id`, nullable `campaign_id`, UTC timestamp, source, and `session_id`.
  - Ingestion is idempotent; duplicate event IDs are ignored.
  - Invalid events are rejected and logged with a reason.
- **Functional Specifications:**
  - `Event` entity (append-only): `event_id` (client-generated, unique), `tracking_session_id`, `test_id`, `product_id`, `campaign_id`, `adset_id`, `ad_variation_id`, `event_type`, `source` (`web | server`), `url`, `referrer`, `occurred_at`, `received_at`, `is_bot`, `properties jsonb`.
  - `ITrackingService.recordEvent(storeId, dto)`; event type must exist in the `EventType` reference table.
  - Idempotency via unique `event_id` — duplicate inserts ignored, not errors.
  - Invalid events rejected with a logged reason (no stack trace, no PII).
  - Indexes on `(store_id, event_type, occurred_at)` and `tracking_session_id`.
- **Notes:** `Event` and `Order` and `MetricSnapshot` are the high-volume tables — partition by month when volume grows.

### FR-4.1.2 Landing-page visit and interaction tracking
- **User Story:** As a merchant, I want page visits and interactions recorded so I can measure funnel entry.
- **Acceptance Criteria:**
  - First-party tracking runs on published pages.
  - Captures page views and defined interactions.
  - Bot traffic is filtered using documented rules.
  - Consent requirements are respected before non-essential tracking.
  - Attribution parameters are captured with the session.
- **Functional Specifications:**
  - `TrackingSession` entity: `landing_page_id`, `test_id`, `campaign_id`, first-touch UTM fields, `referrer`, `user_agent`, `ip_hash char(64)`, `consent_state` (`unknown | granted | denied`), `started_at`, `last_seen_at`.
  - `ITrackingService.createSession(storeId, dto)`; session cookie/identifier issued to the visitor.
  - First-party script on published pages emits `page_view`, `product_view`, `cta_click`, `cod_form_start`.
  - Bot filter rules (user-agent, request rate, known crawler patterns) documented and applied; bots excluded from metrics.
  - Consent gate before non-essential tracking; `ip_hash` only, never raw IP.
- **Notes:** Consent state stored per session and honoured on the ingest endpoint.

### FR-4.1.3 WhatsApp click tracking
- **User Story:** As a merchant, I want WhatsApp clicks tracked so I can measure expressed interest.
- **Acceptance Criteria:**
  - CTA routes through a tracked redirect and then forwards to `wa.me`.
  - Click is associated with product and campaign when attribution data exists.
  - Duplicate clicks within a session window are deduplicated.
  - A WhatsApp click is never counted as a purchase or confirmed order.
- **Functional Specifications:**
  - `ITrackingService.trackWhatsAppClick(sessionId, dto)` → `RedirectResult`; endpoint resolves `TrackingLink.token`, records a `whatsapp_click` event, then 302s to `wa.me`.
  - Association uses the tracking link's campaign/adset/ad variation and the session's product/test.
  - Deduplication window per session + product (configurable) to avoid double counting.
  - Metric layer enforces: `whatsapp_click` never contributes to confirmed orders or deposits.
- **Notes:** Intent signal only — must be labelled as such in the dashboard.

### FR-4.1.4 COD order form and submission
- **User Story:** As a merchant, I want customers to submit COD orders so I can measure purchase intent without online payment.
- **Acceptance Criteria:**
  - Form collects name, phone, address, quantity, and optional variant/notes.
  - Phone and address validation follows the target market's format.
  - Invalid submissions are rejected with field-level errors.
  - Duplicate submissions are guarded against.
  - Valid submissions are stored and linked to product/campaign where available.
  - Rate limiting and spam protection are applied.
- **Functional Specifications:**
  - `ITrackingService.submitCodOrder(storeId, dto)` → `Order` with `origin = cod`, `status = pending`, `test_phase = during_test`.
  - `Order` fields used: `customer_name`, `customer_phone`, `customer_address_enc`, `currency`, `total_minor`, `landing_page_id`, `post_id`, `campaign_id`, `tracking_session_id`, `dedupe_hash`.
  - `OrderItem` line with `quantity > 0`, `unit_price_minor`, `line_total_minor`, `product_name_snapshot`.
  - Field-level validation errors keyed to the form field; market-specific phone and address rules.
  - Duplicate guard via `dedupe_hash` (session + product + payload within window) and unique constraint on `(store_id, dedupe_hash)`.
  - `RateLimitService.checkLimit(key, policy)` plus spam heuristics (honeypot, minimum fill time).
- **Notes:** `Order.customer_address_enc` is ciphertext; PII access is restricted.

### FR-4.1.5 Deposit confirmation
- **User Story:** As a merchant, I want confirmed deposits distinguished from unconfirmed interest.
- **Acceptance Criteria:**
  - Deposits are recorded only through a supported mechanism: manual verification with evidence or a payment webhook.
  - States are pending, confirmed, and rejected.
  - Unverified deposits are never counted as confirmed.
  - Confirmed deposits link to order/product/test where possible.
  - Status changes are audited.
- **Functional Specifications:**
  - `Deposit` entity: `order_id`, `test_id`, `status` (`pending | confirmed | rejected`), `amount_minor`, `currency`, `method` (`manual | payment_gateway`), `evidence_file_id`, `external_payment_id`, `verified_by`, `verified_at`.
  - `ITrackingService.confirmDeposit(orderId, dto)`; manual path requires `evidence_file_id` (`purpose = deposit_evidence`).
  - Payment-webhook path (Phase 2, decision D2) writes `external_payment_id` and `method = payment_gateway`.
  - Confirmed deposits emit `deposit_confirmed` events; pending/rejected never count as confirmed.
  - Every status change audited with actor, before/after.
- **Notes:** MVP uses manual verification with evidence; payment gateway deferred (D2).

### FR-4.1.6 Attribution rules
- **User Story:** As a merchant, I want clear attribution rules so metrics are not misleading.
- **Acceptance Criteria:**
  - A documented attribution model is applied (e.g., last-touch within a session plus campaign parameters).
  - Unattributed events are reported as direct/unknown, never guessed.
  - The attribution window is configurable and versioned.
  - The dashboard displays attribution coverage percentage.
- **Functional Specifications:**
  - `Attribution` entity: `subject_type` (`event | order`), `subject_id`, `test_id`, `campaign_id`, `adset_id`, `ad_variation_id`, `model` (`last_touch | first_touch | direct`), `window_seconds`, `is_attributed`, `confidence`, `resolved_at`; unique `(subject_type, subject_id)`.
  - `IAttributionStrategy.resolve(subjectType, subjectId, context)` → `Attribution`; implementations for `last_touch`, `first_touch`, `direct`.
  - `ITrackingService.resolveAttribution(subjectType, subjectId)` resolves or returns the direct/unknown result.
  - Attribution window configurable per store and versioned with each resolved attribution.
  - Coverage metric: attributed subjects أ· total subjects, shown on the dashboard.
- **Notes:** Decision D4 — no reliable WhatsApp → order identity handoff; use store-scoped token + self-reported order code. Multi-touch deferred.

### FR-4.1.7 Conversion metrics dashboard
- **User Story:** As a merchant, I want to compare visits, WhatsApp clicks, and orders so I can understand customer response.
- **Acceptance Criteria:**
  - Displays visits, WhatsApp clicks, COD submissions, and confirmed deposits by product and campaign.
  - Every rate shows numerator, denominator, and definition.
  - Date range and timezone are selectable.
  - Data freshness (last update) is visible.
  - No metric is labeled "sale" unless verified by order or payment.
- **Functional Specifications:**
  - `ITrackingService.getMetrics(storeId, filters)` → `MetricsResult` grouped by product and campaign.
  - Metric definitions with explicit numerator, denominator, and formula text shipped with the response.
  - Date range + store timezone filters; all timestamps converted for display.
  - Freshness indicator = latest `Event.received_at` / `MetricSnapshot.snapshot_at` in the selected window.
  - Label policy enforced in API and UI: "sale" only for `Order` with confirmed status or a confirmed `Deposit`.
- **Notes:** Dashboard query budget P95 < 2 seconds; pre-aggregate when needed.

## Module 5.1 — Automated Go / No-Go Demand Verdict (P0)

### FR-5.1.1 Retrieve test results
- **User Story:** As a merchant, I want the system to collect all test results so the verdict is based on complete data.
- **Acceptance Criteria:**
  - Pulls spend, impressions, clicks, and tracked conversion events for the test window.
  - Missing or partial data is explicitly identified.
  - A data snapshot is stored with the verdict.
  - Timezone and currency are consistent with the campaign.
- **Functional Specifications:**
  - `IVerdictService.computeSnapshot(testId, period: DateRange)` → `TestResultSnapshot`.
  - `TestResultSnapshot` entity: `test_id`, `period_start`, `period_end`, `currency`, `spend_minor`, `impressions`, `clicks`, `tracked_conversions`, `confirmed_deposits`, `conversion_rate`, `cost_per_conversion_minor`, `data_completeness`, `source_metric_snapshot_ids uuid[]`, `captured_at`.
  - Spend/impressions/clicks sourced from `MetricSnapshot`; conversions from `Event` of the test's primary conversion type.
  - `data_completeness` reflects missing metric sources; partial data recorded explicitly, not silently zero-filled.
- **Notes:** The snapshot is immutable and is the sole input to verdict evaluation.

### FR-5.1.2 Verdict KPI calculation
- **User Story:** As a merchant, I want defined performance indicators so the verdict is understandable.
- **Acceptance Criteria:**
  - Computes conversion rate, cost per tracked conversion, cost per confirmed deposit (or the defined primary conversion), and total spend.
  - Formulas and denominators are documented and visible.
  - Metrics display as N/A when data is unavailable.
- **Functional Specifications:**
  - `conversion_rate = tracked_conversions / clicks` (null when clicks = 0).
  - `cost_per_conversion_minor = spend_minor / tracked_conversions` (null when conversions = 0).
  - `cost_per_confirmed_deposit_minor = spend_minor / confirmed_deposits` (null when no confirmed deposits).
  - Primary conversion selected by `Test.primary_conversion` (`whatsapp_click | cod_order | deposit_confirmed`).
  - Formula strings returned with the snapshot and rendered in the UI.
- **Notes:** Unavailable metrics must render as N/A, never 0.

### FR-5.1.3 Decision rule configuration
- **User Story:** As a merchant, I want configurable decision rules so verdicts match my economics.
- **Acceptance Criteria:**
  - Rules include minimum conversion rate, maximum cost per conversion relative to margin, and minimum spend/clicks.
  - Rules are versioned per store/category, and changes are audited.
  - The active rule set is displayed alongside the verdict.
- **Functional Specifications:**
  - `DecisionRuleSet` entity: `store_id` (null = platform default), `category_id`, `version`, `is_active`, `min_spend_minor`, `min_clicks`, `min_conversions`, `min_confirmed_deposits`, `min_conversion_rate`, `max_cost_per_conversion_minor`, `rules jsonb`, `created_by`.
  - `IVerdictService.upsertDecisionRuleSet(storeId, dto)`; each save creates a new version and deactivates the prior one.
  - Resolution order: campaign/category rule set → store rule set → platform default.
  - Rule changes audited via `IAuditService` (before/after).
  - Active rule set displayed with the verdict (key, version, thresholds).
- **Notes:** `rules jsonb` requires a `schema_version` key.

### FR-5.1.4 Verdict classification
- **User Story:** As a merchant, I want a clear Go, No-Go, or Extend Test classification so I can decide.
- **Acceptance Criteria:**
  - Output is exactly one of Go, No-Go, or Extend Test.
  - Given the same snapshot and rule version, the verdict is deterministic.
  - Go/No-Go cannot be returned when data sufficiency fails.
  - Verdict stores inputs, rule version, and timestamp.
- **Functional Specifications:**
  - `IVerdictService.evaluateVerdict(testId)` → `Verdict`.
  - `IVerdictEvaluator.evaluate(snapshot, ruleSet)` → `VerdictResult`; deterministic rule evaluation, no randomness.
  - `Verdict` entity: `test_id`, `result_snapshot_id`, `decision_rule_set_id`, `outcome` (`go | no_go | extend_test`), `is_conclusive`, `primary_reason`, `limitations jsonb`, `rule_trace jsonb`.
  - Sufficiency gate: if `snapshot.data_completeness` or the rule minimums are unmet → outcome forced to `extend_test`.
  - `Test.status` transitions to `awaiting_verdict` / `completed` / `extended` accordingly.
- **Notes:** `rule_trace` records every rule evaluated, its threshold, observed value, and pass/fail.

### FR-5.1.5 Verdict explanation and limitations
- **User Story:** As a merchant, I want to see why a verdict was reached so I can make an informed decision.
- **Acceptance Criteria:**
  - Displays key metrics and which thresholds were met or missed.
  - Highlights data limitations (small sample, attribution gaps, unverified orders).
  - Distinguishes evidence from assumption.
  - Uses no guarantee-of-outcome language.
- **Functional Specifications:**
  - Explanation rendered from `Verdict.rule_trace` (met/missed thresholds with observed values) and `Verdict.limitations`.
  - Limitations derived from the snapshot: low `data_completeness`, attribution coverage below threshold, unverified COD orders counted as intent only.
  - Evidence vs assumption labels from the snapshot source types (platform metrics vs tracked events).
  - Copy guardrails: no outcome guarantees in verdict surfaces.
- **Notes:** `limitations` and `rule_trace` are JSONB with a `schema_version` key.

### FR-5.1.6 Inconclusive test detection
- **User Story:** As a merchant, I want inconclusive tests identified so I do not act on weak evidence.
- **Acceptance Criteria:**
  - Flags insufficient traffic, spend, conversions, missing tracking, or unreliable attribution.
  - States which specific condition triggered the inconclusive result.
  - Routes the test to Extend Test rather than Go/No-Go.
- **Functional Specifications:**
  - Conditions evaluated: `clicks < min_clicks`, `spend_minor < min_spend_minor`, `tracked_conversions < min_conversions`, `confirmed_deposits < min_confirmed_deposits`, `data_completeness` below threshold, attribution coverage below threshold, no tracking events at all.
  - `Verdict.is_conclusive = false`, `outcome = extend_test`, `primary_reason` names the exact failing condition.
  - Each triggering condition listed in `limitations`.
- **Notes:** Prevents false Go/No-Go outcomes on thin data.

### FR-5.1.7 Extend a test
- **User Story:** As a merchant, I want to extend an inconclusive test so I can gather more evidence.
- **Acceptance Criteria:**
  - Merchant can extend with explicit additional budget and duration.
  - Extension is validated against budget caps.
  - The new window is recorded separately.
  - Verdict is recomputed under a documented policy (combined or new-window data).
  - Prior verdict and data snapshot remain in history.
- **Functional Specifications:**
  - `IVerdictService.extendTest(testId, dto)` → `TestExtension`.
  - `TestExtension` entity: `test_id`, `previous_end_at`, `new_end_at`, `added_budget_minor`, `currency`, `reason`, `approved_by`.
  - Budget validation against `BudgetPolicy` total/daily caps and `Test.total_budget_minor`; over-cap requests rejected.
  - `Test.status = extended`, `planned_end_at` / `total_budget_minor` updated; actuals untouched.
  - Recompute policy configurable: combined window or new-window only; the policy used is recorded with the verdict.
  - Prior `Verdict` and `TestResultSnapshot` rows are never modified or deleted.
- **Notes:** Extension requires Owner/Manager approval per FR-0.2.

## Module 5.2 — Predictive Batch Quantity and Investment Recommendation (P0)

### FR-5.2.1 Collect investment inputs
- **User Story:** As a store owner, I want to enter costs and budget so recommendations reflect my constraints.
- **Acceptance Criteria:**
  - Collects unit cost, selling price, fulfillment/shipping, payment fees, available budget, target margin, supplier MOQ, and lead time.
  - Values are range-validated and currency-consistent.
  - Missing values are flagged explicitly, never silently defaulted.
  - Inputs are saved per product/test.
- **Functional Specifications:**
  - `InvestmentProfile` entity: `test_id`, `version`, `unit_cost_minor`, `selling_price_minor`, `fulfillment_cost_minor`, `payment_fee_bp`, `available_budget_minor`, `target_margin_bp`, `supplier_moq`, `lead_time_days`, `currency`, `is_current`, `created_by`; unique `(test_id, version)`.
  - `IInvestmentService.upsertProfile(testId, dto)`; each save creates a new version and demotes the prior current row.
  - Validation: non-negative amounts, `payment_fee_bp` and `target_margin_bp` within 0–10000, `supplier_moq >= 1`, `lead_time_days >= 0`, single currency across all inputs.
  - Missing inputs returned as an explicit list of missing fields; no default substitution.
- **Notes:** `Money` value object enforces minor units and currency consistency.

### FR-5.2.2 Demand estimation with stated assumptions
- **User Story:** As a store owner, I want a demand estimate that explains its assumptions so I understand the risk.
- **Acceptance Criteria:**
  - Converts test conversion data into a low/base/high demand range.
  - Assumptions are explicit: traffic source, repeat rate, seasonality, and attribution adjustment.
  - Confidence and limitations are displayed.
  - No single-point certainty is presented.
- **Functional Specifications:**
  - `IDemandEstimator.estimate(snapshot: TestResultSnapshot, profile: InvestmentProfile)` → `DemandEstimate`.
  - `DemandEstimate` entity: `investment_recommendation_id`, `low_units`, `base_units`, `high_units`, `assumptions jsonb`, `confidence` (`high | medium | low`).
  - Assumptions stored explicitly: traffic source, repeat rate, seasonality factor, attribution adjustment factor — each with a value and source.
  - Confidence derived from snapshot data completeness and sample size; limitations attached to the recommendation.
  - Always rendered as a range; no single-point output.
- **Notes:** `assumptions jsonb` requires a `schema_version` key; range ordering enforced low ≤ base ≤ high.

### FR-5.2.3 Unit economics
- **User Story:** As a store owner, I want unit economics so I can judge profitability before ordering.
- **Acceptance Criteria:**
  - Computes contribution margin per unit (price − COGS − fulfillment − fees).
  - Computes break-even units and CAC from test spend and conversions.
  - Formulas are displayed.
  - Negative-margin scenarios are clearly flagged.
- **Functional Specifications:**
  - `IInvestmentCalculator.calculateEconomics(profile, demand)` → `UnitEconomics`.
  - `UnitEconomics` entity: `investment_recommendation_id`, `contribution_margin_minor`, `break_even_units numeric(12,2)`, `cac_minor`, `formulas jsonb`, `is_negative_margin`.
  - `contribution_margin_minor = selling_price_minor − unit_cost_minor − fulfillment_cost_minor − (selling_price_minor أ— payment_fee_bp / 10000)`.
  - `break_even_units = available_budget_minor / contribution_margin_minor` (undefined for a negative margin).
  - `cac_minor = spend_minor / tracked_conversions` from the test snapshot.
  - `formulas jsonb` stores the rendered formula text for display.
- **Notes:** Negative margin is flagged prominently, not just numerically.

### FR-5.2.4 Compute feasible order quantities
- **User Story:** As a store owner, I want recommended quantities that respect my budget and supplier constraints.
- **Acceptance Criteria:**
  - Proposes at least two scenarios (e.g., conservative, base, aggressive) when data is sufficient.
  - Scenarios respect MOQ, budget, and the demand range.
  - Infeasible scenarios are excluded with an explanation.
  - If no scenario is feasible, the system explains why instead of returning a number.
- **Functional Specifications:**
  - `IInvestmentCalculator.generateScenarios(profile, demand, economics)` → `List<QuantityScenario>`.
  - `QuantityScenario` entity: `investment_recommendation_id`, `label` (`conservative | base | aggressive`), `quantity`, `inventory_cost_minor`, `expected_units_sold_low/high`, `revenue_low/high_minor`, `profit_low/high_minor`, `sell_through_low/high`, `overstock_risk`, `stockout_risk`, `is_feasible`, `infeasibility_reason`.
  - Constraints applied: `quantity >= supplier_moq`, `quantity أ— unit_cost_minor <= available_budget_minor`, quantity aligned to the demand range.
  - Scenario quantities derived from the demand range (low / base / high).
  - Infeasible scenarios excluded with a reason; when no scenario passes, return an explanation instead of numbers.
- **Notes:** Lead time is surfaced as a constraint note (arrival before or after the selling window).

### FR-5.2.5 Scenario presentation and risk
- **User Story:** As a store owner, I want compare quantities so I understand the trade-off between risk and opportunity.
- **Acceptance Criteria:**
  - Each scenario shows inventory cost, expected units sold, revenue range, profit range, and sell-through %.
  - Overstock risk and stockout risk are highlighted per scenario.
  - Estimates are labeled as projections, not guarantees.
  - Assumptions are listed for each scenario.
- **Functional Specifications:**
  - Scenario card UI renders: inventory cost, expected units sold (low–high), revenue range, profit range, sell-through %, overstock risk, stockout risk.
  - Risk computed from `expected_units_sold_low` vs `quantity` (overstock) and `expected_units_sold_high` vs `quantity` (stockout), labelled `low | medium | high`.
  - "Projection" labeling on all estimated figures; no guarantee wording.
  - Assumptions rendered from `DemandEstimate.assumptions` plus per-scenario notes.
- **Notes:** Ranges, not point values, in the UI.

### FR-5.2.6 Adjust assumptions and recalculate with versioning
- **User Story:** As a store owner, I want to change assumptions and recalculate so I can evaluate alternatives.
- **Acceptance Criteria:**
  - Merchant can edit supported assumptions, costs, and budget.
  - Recalculation produces a new version.
  - Original and revised assumptions are visually distinguishable.
  - Version history is retained and recommendations update accordingly.
- **Functional Specifications:**
  - `IInvestmentService.recalculate(testId, profileId, overrides)` → `InvestmentRecommendation`.
  - `InvestmentRecommendation` entity: `test_id`, `investment_profile_id`, `version`, `summary`, `assumptions_snapshot jsonb`, `is_current`, `created_by`; unique `(test_id, version)`.
  - Recalculation creates a new `InvestmentRecommendation` plus fresh `DemandEstimate`, `UnitEconomics`, and `QuantityScenario` rows; the prior version is retained and demoted to `is_current = false`.
  - Diff view compares `assumptions_snapshot` of the prior and current versions, highlighting changed fields.
  - `IInvestmentService.getHistory(testId)` lists all recommendation versions; `getRecommendation(testId)` returns the current one.
- **Notes:** Prior recommendation versions are never mutated.

## Module 4.2 — Optimization (MVP cut: recommendations only)

### FR-4.2.5 Optimization recommendations (MVP, recommend-only)
- **User Story:** As a merchant, I want recommended actions I can approve so optimization stays under my control.
- **Acceptance Criteria:**
  - Generates recommendations such as pause, keep, or reallocate, with rationale and expected impact.
  - Merchant can accept or dismiss each recommendation.
  - No automatic change occurs in this mode.
  - Recommendations never exceed the approved budget cap.
- **Functional Specifications:**
  - `OptimizationRecommendation` entity: `finding_id`, `campaign_id`, `adset_id`, `ad_variation_id`, `action` (`pause | keep | reallocate | increase_budget | decrease_budget`), `rationale`, `proposed_changes jsonb`, `expected_impact jsonb`, `budget_impact_minor`, `currency`, `status` (`pending | accepted | dismissed | executed | expired`).
  - `IOptimizationService.getRecommendations(campaignId, status?)`, `.acceptRecommendation(id, actorId)`, `.dismissRecommendation(id, actorId)`.
  - Accepting records merchant intent only — no platform write is performed in MVP.
  - `BudgetPolicy` caps enforced when generating the proposal: no recommendation may exceed the total or daily cap.
  - Acceptance/dismissal audited with actor and before/after status.
- **Notes:** Deferred from MVP: FR-4.2.6 automated execution, FR-4.2.7 kill switch execution paths. `OptimizationAction` and `BudgetPolicy` entities exist for Phase 2.

## Cross-Cutting Acceptance Criteria (apply to every task)

- **CC-1** — Authorization is enforced server-side on every endpoint.
- **CC-2** — Validation exists on both client and server; errors are specific and actionable.
- **CC-3** — No stack traces, secrets, or unnecessary PII appear in user-facing errors or logs.
- **CC-4** — Timestamps are stored in UTC and displayed in the store timezone; money is stored in minor units with currency.
- **CC-5** — Merchant-facing UI and generated pages support required languages and RTL layouts.
- **CC-6** — Generated landing pages meet a WCAG 2.1 AA baseline.
- **CC-7** — PII is minimized, encrypted at rest/in transit, and collected only with required consent.
- **CC-8** — External calls use rate limiting, retries with backoff, timeouts, and idempotency.
- **CC-9** — Structured logs, metrics, and job IDs exist for all async workflows.
- **CC-10** — Performance budgets: page generation P95 ≤ 5 minutes; dashboard queries P95 < 2 seconds.
- **CC-11** — Test coverage includes unit, integration, tenant-isolation, and end-to-end tests for critical flows.

## Open Decisions (must be resolved before the dependent task starts)

| # | Decision | Blocks |
|---|---|---|
| D1 | Which ad platforms for MVP (Meta only vs Meta+TikTok+Google) | FR-1.1.6, FR-3.2.x |
| D2 | Deposit verification: manual admin vs payment gateway | FR-4.1.5 |
| D3 | Competitive/market data source: licensed API vs public data vs LLM knowledge | FR-2.2.x |
| D4 | Attribution model for WhatsApp → order | FR-4.1.6 |
| D5 | Auto-optimization in MVP — recommend-only is the chosen default | FR-4.2.5 |
| D6 | Scoring approach: rules-based weighted (chosen for v1) vs ML | FR-2.1.4 |
| D7 | Multi-store per merchant — MVP is 1 store per user via `Store.owner_user_id` | FR-0.2, FR-0.1 |
| D8 | Markets, currencies, RTL languages in v1 | FR-3.1.x, FR-4.1.4 |

## Suggested Delivery Slices

| Slice | Contents | Depends on |
|---|---|---|
| **0 — Database schema (blocking)** | DB-0.1–DB-0.24 (schema, integrity, indexes, RLS, concurrency, PII, roles, CI, performance, retention, docs) | — |
| **A — Foundation & onboarding** | FR-0.x, FR-1.1.1–1.1.5, FR-1.2.x | 0 |
| **B — Concept evaluation** | FR-2.1.x, FR-1.1.6 (integration import) | A (sales + profile data) |
| **C — Recommendations & assets** | FR-2.2.x, FR-3.1.x, FR-3.2.x | B (concepts), D1/D3 |
| **D — Measurement** | FR-4.1.x | C (live pages and campaigns) |
| **E — Decision & investment** | FR-5.1.x, FR-5.2.x | D (test results) |
| **F — Optimization** | FR-4.2.5 only (recommendations) | D + one complete test cycle |

**Recommended MVP cut:** 0 + A + B + C + D + E, with FR-4.2.5 recommendations only.
**Hard rule:** No application module starts before Phase 0 (DB-0.1–DB-0.24) is green, with DB-0.21 (CI pipeline) reporting success.

**Explicitly deferred:** Automated budget reallocation (FR-4.2.6), real-time streaming optimization, multi-touch attribution, payment processing, payment-gateway deposit verification (D2), inventory/warehouse sync, mobile apps, and multi-user collaboration beyond the defined roles.


