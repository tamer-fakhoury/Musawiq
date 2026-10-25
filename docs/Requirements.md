# Refined Requirements & User Stories

## Analysis Summary

The source requirements are strong on intent but have three structural weaknesses: **compound requirements** (multiple testable behaviors in one FR), **undefined decision terms** ("sufficient data", "viability score", "supported platform"), and **implicit platform requirements** (tenant isolation, audit, idempotency) that the acceptance criteria silently depend on.

Four changes were applied:

1. **Split compound FRs** into atomic, independently testable requirements.
2. **Added data-sufficiency gates** before scoring and verdicts, so the system returns "insufficient data" instead of false confidence.
3. **Separated recommendation from execution** for campaign optimization (recommend-only in MVP).
4. **Added provenance and versioning** for AI output, scores, profiles, decision rules, and investment assumptions.

### Decisions needed before build

| # | Decision | Impact |
|---|---|---|
| D1 | Which ad platforms for MVP (Meta only vs Meta+TikTok+Google) | API approval lead time, schema differences |
| D2 | Deposit verification: manual admin vs payment gateway | Payment/compliance scope, large effort delta |
| D3 | Competitive/market data source: licensed API vs public data vs LLM knowledge | Legal risk, freshness, evidence quality |
| D4 | Attribution model for WhatsApp → order (no reliable identity handoff) | Metric honesty; use store-scoped token + self-reported order code |
| D5 | Auto-optimization in MVP? | Recommend strongly: **recommend-only** first |
| D6 | Scoring approach: rules-based weighted vs ML | Explainability and reproducibility favor rules-based v1 |
| D7 | Multi-store per merchant? | Affects data model (`store_id`) and permissions |
| D8 | Markets, currencies, RTL languages in v1 | Copy generation, address/phone validation, page layout |

---

# Refined Requirements

Priority: **P0** = MVP critical, **P1** = required for full loop, **P2** = later/advanced.

---

## Module 0 — Platform Foundations (inferred, P0)

### FR-0.1 Store data isolation
**User story:** As a merchant, I want my store data isolated so that no other merchant can access or affect it.
**Acceptance criteria:**
- Every tenant-owned domain record carries a `store_id`; all reads and writes are scoped to the authenticated store. The tenant root (`Store`) is the documented exception — it owns the boundary and carries no `store_id`.
- Platform-global reference rows (e.g., default scoring models, rule sets) may have a null `store_id`; they are read-only to merchants and writable only by the maintenance/owner role.
- Cross-store access returns `403/404` and is logged as a security event.
- Automated tests cover isolation for imports, concepts, campaigns, events, and metrics.
- Store deletion follows a documented retention/deletion process.

### FR-0.2 Roles and spend approval
**User story:** As a store owner, I want to control who can publish pages, launch campaigns, and approve spend.
**Acceptance criteria:**
- A documented permission matrix exists for Owner, Manager, and Analyst roles.
- Only Owner/Manager can publish pages, submit campaigns, or approve budget changes.
- Every privileged action is attributed to a user.
- Unauthorized attempts are blocked with a clear message.

### FR-0.3 Audit trail
**User story:** As an owner, I want an immutable record of consequential actions so I can investigate changes.
**Acceptance criteria:**
- Logs capture actor, store, action, target, UTC timestamp, and before/after values for import commits, publications, budget changes, verdicts, and optimization actions.
- Logs are append-only and retained for a configurable period (default ≥12 months).
- Owner can filter and export by date, user, and target.
- Log entries cannot be edited through the UI or API.

### FR-0.4 Async jobs, idempotency, and status
**User story:** As a merchant, I want long-running operations to be reliable and not create duplicates when I retry.
**Acceptance criteria:**
- Imports, page generation, ad publication, and metric sync run as background jobs with states: queued, running, succeeded, failed, partial.
- Retrying with the same idempotency key does not duplicate records or campaigns.
- Failures expose a human-readable reason plus a job/correlation ID.
- UI shows last-updated time and offers a safe manual retry.

### FR-0.5 AI/model governance and degraded mode
**User story:** As a platform operator, I want AI outputs to be versioned and safely degradable so the product remains trustworthy.
**Acceptance criteria:**
- Each AI output or score stores model/prompt/template version, input snapshot reference, and timestamp.
- Merchant data is not used to train shared models without explicit opt-in.
- If an AI or ad-platform dependency is unavailable, the flow degrades gracefully with a clear message, retry option, and manual fallback.
- AI-generated content is labeled as such in the UI; the system never fabricates evidence or results.

---

## Module 1.1 — Historical Store Data Import

### FR-1.1.1 CSV upload and format validation (+ file limits)
**User story:** As a merchant, I want to upload a CSV of my historical sales so that I can reuse existing data without manual entry.
**Acceptance criteria:**
- Accepts `.csv` up to a configured limit (e.g., 20 MB) with a downloadable template.
- Rejects unsupported type, encoding, or empty files with a specific error.
- Uploaded files are staged only; no sales records are written at this step.
- Success or failure is reported unambiguously.

### FR-1.1.2 Column mapping
**User story:** As a merchant, I want to map my columns to the required fields so my records are interpreted correctly.
**Acceptance criteria:**
- Required fields: `product_id`, `product_name`, `order_date`, `quantity`, `sales_amount`; optional: `order_id`, `currency`, `sku`.
- System auto-suggests mappings; merchant can override; one source column maps to one target field.
- Sample values are shown per column.
- Import cannot proceed while a required field is unmapped.
- Mapping is saved per store for reuse.

### FR-1.1.3 Row validation and duplicate detection
**User story:** As a merchant, I want invalid rows identified before import so I can fix them.
**Acceptance criteria:**
- Validates required values, date parsing (store timezone), integer quantity > 0, numeric amount ≥ 0, valid currency, and product consistency.
- Duplicate rules are explicit: same `order_id` + `product_id`, or same product/date/quantity/amount when no order ID exists.
- Duplicates are detected both within the file and against existing records.
- Errors return row number, field, reason, and raw value.
- The merchant explicitly chooses strict (all-or-nothing) or lenient (skip invalid rows) mode.

### FR-1.1.4 Preview and error review before commit
**User story:** As a merchant, I want to review imported records and errors before saving so I can verify accuracy.
**Acceptance criteria:**
- Displays a sample of valid rows plus all errors (paginated or downloadable as an error report).
- Displays counts: total, valid, invalid, duplicates.
- Nothing is persisted before explicit confirmation.
- Cancel leaves the database unchanged.

### FR-1.1.5 Commit and import summary
**User story:** As a merchant, I want a clear summary after import so I know exactly what was accepted.
**Acceptance criteria:**
- Commit is transactional; accepted rows are written with an `import_id`.
- Summary shows imported, skipped, rejected, duplicates, duration, and date range.
- Import history is viewable and the error report is re-downloadable.
- Re-uploading the same file warns about duplicates and respects idempotency.
- The update policy for existing records is explicit; no silent overwrite.

### FR-1.1.6 E-commerce integration connect and historical import
**User story:** As a merchant, I want to connect my store so I can import historical data without exporting it manually.
**Acceptance criteria:**
- Supported platform connects via OAuth/API key with read-only catalog and order scopes.
- Credentials are encrypted at rest; disconnect revokes access and stops syncing.
- Merchant selects a date range; products and orders map to the canonical schema.
- Progress and per-entity results are displayed; partial failures list reasons and support safe retry.
- Imported records are deduplicated against CSV imports.

---

## Module 1.2 — Customer Preference and Audience Profiling

### FR-1.2.1 Product category and niche
**User story:** As a store manager, I want to select my category and niche so recommendations match my business.
**Acceptance criteria:**
- Merchant can select one or more categories from a taxonomy.
- Merchant can add a custom niche within a defined length limit.
- At least one category is required.
- Selection is saved to the store profile.

### FR-1.2.2 Target customer profile
**User story:** As a store manager, I want to define my target audience so evaluations reflect my intended customers.
**Acceptance criteria:**
- Captures target location(s), age range, interests, and preferred language(s).
- Age range rejects inverted or out-of-bounds values.
- Multiple audience segments are supported.
- Optional fields may be left empty.
- Saved profile is editable.

### FR-1.2.3 Customer feedback intake
**User story:** As a store manager, I want to submit customer feedback so recommendations account for stated needs.
**Acceptance criteria:**
- Accepts manual text entry or a supported file (`.csv`, `.txt`, `.xlsx`), with type/size/encoding validation.
- Each feedback item is timestamped and linked to the correct store.
- Rejected input returns a specific reason.
- PII handling and consent are documented where feedback may contain personal data.

### FR-1.2.4 Save, version, and consume audience profile
**User story:** As a store manager, I want profile updates to apply predictably to future evaluations.
**Acceptance criteria:**
- Each save creates a new profile version.
- Evaluations record which profile version was used.
- Editing the profile does not retroactively change past evaluations.
- Version history is viewable.

---

## Module 2.1 — Proprietary Product Assessment and Scoring

### FR-2.1.1 Create a product concept with validation
**User story:** As a brand owner, I want to enter my product details so the platform can evaluate the concept.
**Acceptance criteria:**
- Captures name, description, category, proposed price, estimated cost, currency, and optional image.
- Required-field and image type/size validation are enforced inline.
- Gross margin is computed and displayed.
- Concepts can be saved as drafts and belong to one store.

### FR-2.1.2 Manage multiple concepts and lifecycle
**User story:** As a brand owner, I want to submit and manage multiple concepts so I can prioritize a portfolio.
**Acceptance criteria:**
- Merchant can list, create, edit, archive, and search concepts.
- States are explicit: draft, evaluated, selected, archived.
- Evaluated concepts cannot be hard-deleted.
- List is sortable by score, category, and date.

### FR-2.1.3 Data sufficiency assessment
**User story:** As a brand owner, I want to know whether there is enough data before trusting a score.
**Acceptance criteria:**
- Checks sales history volume/period, audience completeness, price/cost, and optional competitive data.
- Returns per-input status: available, missing, stale, insufficient.
- Missing critical inputs block scoring or flag it as low-confidence per policy.
- The system never silently imputes critical missing inputs.

### FR-2.1.4 Viability scoring
**User story:** As a brand owner, I want a viability score so I can prioritize before paying for tests.
**Acceptance criteria:**
- Produces a score on a documented scale using a versioned, documented model.
- Same inputs and model version produce the same score.
- Inputs, weights, and model version are recorded with each score.
- Score is reported as unavailable (not zero) when critical inputs are missing.
- Batch evaluation of multiple concepts is supported.

### FR-2.1.5 Score explanation and limitations
**User story:** As a brand owner, I want to understand what drives a score so I can judge its reliability.
**Acceptance criteria:**
- Displays the top positive and negative contributing factors with contribution values.
- Displays confidence and limitations (missing competitive data, small sample, stale history).
- Distinguishes measured inputs from inferred values.
- Makes no guarantee-of-sales claims.

### FR-2.1.6 Compare, sort, and select concepts
**User story:** As a brand owner, I want to compare scores so I can choose which concepts to test first.
**Acceptance criteria:**
- Side-by-side comparison of evaluated concepts with score and key metrics.
- Sorting and filtering by score, category, and date.
- Merchant can select one or more concepts to advance to Stage 2.
- Selection is recorded and visible in the concept state.

---

## Module 2.2 — Automated Product Recommendation Engine

### FR-2.2.1 Generate recommendations
**User story:** As a merchant, I want product ideas based on my niche and audience so I can find expansion opportunities.
**Acceptance criteria:**
- On-demand generation uses niche, audience profile, sales history, and trend/competitive data when available.
- Returns a configurable number of ideas.
- Deduplicates against existing concepts and previously dismissed ideas.
- Generation metadata (inputs, model version, timestamp) is stored.

### FR-2.2.2 Rationale and evidence provenance
**User story:** As a merchant, I want to understand why an idea is recommended so I can judge relevance.
**Acceptance criteria:**
- Each idea includes a description, rationale, and evidence list.
- Every evidence item is labeled **Verified** (source, date, link) or **AI Hypothesis**.
- No fabricated sources or links are displayed.
- Stale evidence is flagged.
- Verified and hypothesized evidence are visually distinct.

### FR-2.2.3 Save or dismiss ideas
**User story:** As a merchant, I want to save or dismiss ideas so my library stays relevant.
**Acceptance criteria:**
- Merchant can save an idea to the library or dismiss it with an optional reason.
- Dismissed ideas are not re-suggested unless restored.
- State persists per store and per user.

### FR-2.2.4 Convert an idea into a product concept
**User story:** As a merchant, I want to turn an idea into a concept so I can evaluate it.
**Acceptance criteria:**
- Conversion prefills an editable concept with the idea's details.
- Concept links back to its source idea; source is marked as converted.
- Merchant must confirm conversion.
- Converted concept enters the FR-2.1 evaluation flow.

---

## Module 3.1 — Automated Micro-Landing Page Builder

### FR-3.1.1 Product input and page options
**User story:** As an e-commerce seller, I want to enter product details and options so a page can be generated.
**Acceptance criteria:**
- Captures image (JPG/PNG/WebP with type and size limits), name, description, price, currency, language, target market, and order method.
- Mandatory fields are validated before generation.
- Draft input is autosaved.
- Order method options are WhatsApp or COD.

### FR-3.1.2 Generate a responsive landing page
**User story:** As an e-commerce seller, I want a generated page so I do not have to build one manually.
**Acceptance criteria:**
- Uses a predefined responsive template containing image, name, description, price, and CTA.
- Renders correctly on mobile and desktop breakpoints.
- Generation completes within 5 minutes at P95 under stated supported conditions.
- Failures are reported with a reason and are retryable.

### FR-3.1.3 Product copy generation and editing
**User story:** As an e-commerce seller, I want copy in my market's language so the page fits my audience.
**Acceptance criteria:**
- Generates copy in the selected language and market, including RTL layout where applicable.
- Merchant can regenerate and edit all copy.
- Generated copy avoids unverifiable medical, absolute, or guaranteed claims.
- Edits persist in the draft.

### FR-3.1.4 Ordering mechanism
**User story:** As an e-commerce seller, I want WhatsApp or COD ordering so customers can order in the way they expect.
**Acceptance criteria:**
- WhatsApp option produces a `wa.me` deep link with a prefilled message and attribution token.
- COD option renders a form with required fields.
- Selected mechanism appears on the published page.
- Link or form is verified working before publish.

### FR-3.1.5 Preview, edit, publish, and shareable URL
**User story:** As an e-commerce seller, I want to review and publish my page so I keep control of presentation.
**Acceptance criteria:**
- Preview is available in desktop and mobile views.
- Merchant can edit supported text and product details.
- Publish requires explicit confirmation and valid mandatory fields.
- Successful publish returns a live HTTPS URL.
- Published pages can be updated or unpublished; an unpublished URL stops serving or shows an unavailable state.
- Generated pages meet a baseline accessibility check (alt text, labels, contrast).

---

## Module 3.2 — Dynamic Social Ad Creative and Campaign Setup

### FR-3.2.1 Generate ad copy variations
**User story:** As a digital marketer, I want multiple ad copy variations so I can test different messages.
**Acceptance criteria:**
- Generates a configurable number of distinct variations (default 3–5) from product and landing-page data.
- Respects platform character limits and the campaign language.
- Each variation is linked to the correct product.
- Near-duplicate variations are flagged.

### FR-3.2.2 Review, edit, approve, or discard variations
**User story:** As a digital marketer, I want to curate variations so only approved messages run.
**Acceptance criteria:**
- Each variation can be edited, approved, or discarded.
- Status is visible for every variation.
- Only approved variations are eligible for publication.
- At least one approved variation is required to proceed.

### FR-3.2.3 Campaign configuration
**User story:** As a digital marketer, I want to configure platform, audience, budget, and duration so the test has defined parameters.
**Acceptance criteria:**
- Captures platform, objective, audience (location/age/interests or saved audience), budget, currency, and start/end or duration.
- Validates minimum budget, valid dates, and required fields.
- Configuration is saved as a draft before submission.

### FR-3.2.4 Campaign association and tracking parameters
**User story:** As a digital marketer, I want the campaign linked to its product and page so results are attributable.
**Acceptance criteria:**
- Campaign links to exactly one product and one landing page.
- UTM/click parameters are generated and embedded in the ad destination.
- Association is visible on the campaign detail screen.
- Missing or invalid tracking parameters block publication.

### FR-3.2.5 Validation and preview before submission
**User story:** As a digital marketer, I want a pre-flight check so I do not submit an invalid campaign.
**Acceptance criteria:**
- Pre-flight verifies connected account, approved creative, valid budget, live landing page, and tracking parameters.
- Ad preview is displayed.
- Submission is blocked with a specific list of unresolved items.

### FR-3.2.6 Advertising account authorization
**User story:** As a digital marketer, I want to connect an ad account so the platform can publish campaigns.
**Acceptance criteria:**
- OAuth connection to each supported platform with minimal scopes.
- Tokens are encrypted and refreshed; disconnect is supported.
- Connection status and account identity are displayed.
- Expired or revoked authorization is surfaced before submission.

### FR-3.2.7 Publish campaign and report status
**User story:** As a digital marketer, I want to publish an approved campaign and see the result so I can launch without manual recreation.
**Acceptance criteria:**
- Publication requires explicit merchant approval.
- Submission is idempotent and returns the platform campaign ID.
- Status states include submitted, active, rejected, failed, and paused.
- Platform API errors are mapped to actionable messages.
- Retry does not create duplicate campaigns.

---

## Module 4.1 — Behavioral Tracking and Regional Conversion Intent

### FR-4.1.1 Event model and ingestion
**User story:** As a merchant, I want consistent event tracking so I can compare intent signals reliably.
**Acceptance criteria:**
- Canonical events: `page_view`, `product_view`, `cta_click`, `whatsapp_click`, `cod_form_start`, `cod_order_submitted`, `deposit_confirmed`.
- Each event has `event_id`, `store_id`, `product_id`, nullable `campaign_id`, UTC timestamp, source, and `session_id`.
- Ingestion is idempotent; duplicate event IDs are ignored.
- Invalid events are rejected and logged with a reason.

### FR-4.1.2 Landing-page visit and interaction tracking
**User story:** As a merchant, I want page visits and interactions recorded so I can measure funnel entry.
**Acceptance criteria:**
- First-party tracking runs on published pages.
- Captures page views and defined interactions.
- Bot traffic is filtered using documented rules.
- Consent requirements are respected before non-essential tracking.
- Attribution parameters are captured with the session.

### FR-4.1.3 WhatsApp click tracking
**User story:** As a merchant, I want WhatsApp clicks tracked so I can measure expressed interest.
**Acceptance criteria:**
- CTA routes through a tracked redirect and then forwards to `wa.me`.
- Click is associated with product and campaign when attribution data exists.
- Duplicate clicks within a session window are deduplicated.
- A WhatsApp click is never counted as a purchase or confirmed order.

### FR-4.1.4 COD order form and submission
**User story:** As a merchant, I want customers to submit COD orders so I can measure purchase intent without online payment.
**Acceptance criteria:**
- Form collects name, phone, address, quantity, and optional variant/notes.
- Phone and address validation follows the target market's format.
- Invalid submissions are rejected with field-level errors.
- Duplicate submissions are guarded against.
- Valid submissions are stored and linked to product/campaign where available.
- Rate limiting and spam protection are applied.

### FR-4.1.5 Deposit confirmation
**User story:** As a merchant, I want confirmed deposits distinguished from unconfirmed interest.
**Acceptance criteria:**
- Deposits are recorded only through a supported mechanism: manual verification with evidence or a payment webhook.
- States are pending, confirmed, and rejected.
- Unverified deposits are never counted as confirmed.
- Confirmed deposits link to order/product/test where possible.
- Status changes are audited.

### FR-4.1.6 Attribution rules
**User story:** As a merchant, I want clear attribution rules so metrics are not misleading.
**Acceptance criteria:**
- A documented attribution model is applied (e.g., last-touch within a session plus campaign parameters).
- Unattributed events are reported as direct/unknown, never guessed.
- The attribution window is configurable and versioned.
- The dashboard displays attribution coverage percentage.

### FR-4.1.7 Conversion metrics dashboard
**User story:** As a merchant, I want to compare visits, WhatsApp clicks, and orders so I can understand customer response.
**Acceptance criteria:**
- Displays visits, WhatsApp clicks, COD submissions, and confirmed deposits by product and campaign.
- Every rate shows numerator, denominator, and definition.
- Date range and timezone are selectable.
- Data freshness (last update) is visible.
- No metric is labeled "sale" unless verified by order or payment.

---

## Module 4.2 — Real-Time Campaign Optimization

### FR-4.2.1 Scheduled metrics sync
**User story:** As a merchant, I want current campaign metrics so I can see how budget is performing.
**Acceptance criteria:**
- Metrics are pulled per platform at a configurable interval (e.g., 15–60 minutes).
- Platform rate limits are respected; failures retry with backoff.
- Raw and normalized metrics are stored.
- Last successful sync and staleness are displayed.

### FR-4.2.2 KPI calculation
**User story:** As a merchant, I want standard metrics so I can compare performance.
**Acceptance criteria:**
- Computes CTR, CPC, CPM, reach, frequency, engagement, spend, and cost per tracked conversion with documented formulas.
- Unavailable metrics display as N/A, not zero.
- Currency and timezone are normalized consistently.

### FR-4.2.3 Thresholds and minimum-data configuration
**User story:** As a merchant, I want to set thresholds so optimization reflects my risk tolerance.
**Acceptance criteria:**
- Thresholds are configurable globally and per campaign.
- Minimum impressions, clicks, or conversions are configurable.
- Evaluation is skipped with "insufficient data" until minimums are met.
- Threshold changes are versioned and audited.

### FR-4.2.4 Underperformer and promising-ad detection
**User story:** As a merchant, I want weak ads identified so I can avoid wasted spend.
**Acceptance criteria:**
- Flags ads against configured thresholds with a reason code.
- Each flag states the metric, observed value, threshold, and evaluation timestamp.
- No flag is produced when minimum data is not met.
- Promising ads are flagged using the same rule framework.

### FR-4.2.5 Optimization recommendations (MVP)
**User story:** As a merchant, I want recommended actions I can approve so optimization stays under my control.
**Acceptance criteria:**
- Generates recommendations such as pause, keep, or reallocate, with rationale and expected impact.
- Merchant can accept or dismiss each recommendation.
- No automatic change occurs in this mode.
- Recommendations never exceed the approved budget cap.

### FR-4.2.6 Approved or opt-in automated execution (Phase 2)
**User story:** As a merchant, I want the option to automate approved optimizations once tracking is reliable.
**Acceptance criteria:**
- Executes only merchant-approved actions, or actions in an explicitly enabled auto mode.
- Per-action approval is the default.
- Auto mode requires explicit opt-in and shows a clear risk notice.
- Every automated action can be disabled immediately and has a documented reversal path.

### FR-4.2.7 Budget guardrails, audit, and kill switch
**User story:** As a merchant, I want hard budget limits so automation can never overspend.
**Acceptance criteria:**
- Hard total budget cap and optional daily cap are enforced before any change.
- No change that would exceed the cap is submitted.
- Every action logs reason, before/after values, timestamp, and actor (user or system).
- A one-click kill switch halts all automated actions.
- Anomalous spend triggers an alert.

---

## Module 5.1 — Automated Go / No-Go Demand Verdict

### FR-5.1.1 Retrieve test results
**User story:** As a merchant, I want the system to collect all test results so the verdict is based on complete data.
**Acceptance criteria:**
- Pulls spend, impressions, clicks, and tracked conversion events for the test window.
- Missing or partial data is explicitly identified.
- A data snapshot is stored with the verdict.
- Timezone and currency are consistent with the campaign.

### FR-5.1.2 Verdict KPI calculation
**User story:** As a merchant, I want defined performance indicators so the verdict is understandable.
**Acceptance criteria:**
- Computes conversion rate, cost per tracked conversion, cost per confirmed deposit (or the defined primary conversion), and total spend.
- Formulas and denominators are documented and visible.
- Metrics display as N/A when data is unavailable.

### FR-5.1.3 Decision rule configuration
**User story:** As a merchant, I want configurable decision rules so verdicts match my economics.
**Acceptance criteria:**
- Rules include minimum conversion rate, maximum cost per conversion relative to margin, and minimum spend/clicks.
- Rules are versioned per store/category, and changes are audited.
- The active rule set is displayed alongside the verdict.

### FR-5.1.4 Verdict classification
**User story:** As a merchant, I want a clear Go, No-Go, or Extend Test classification so I can decide.
**Acceptance criteria:**
- Output is exactly one of Go, No-Go, or Extend Test.
- Given the same snapshot and rule version, the verdict is deterministic.
- Go/No-Go cannot be returned when data sufficiency fails.
- Verdict stores inputs, rule version, and timestamp.

### FR-5.1.5 Verdict explanation and limitations
**User story:** As a merchant, I want to see why a verdict was reached so I can make an informed decision.
**Acceptance criteria:**
- Displays key metrics and which thresholds were met or missed.
- Highlights data limitations (small sample, attribution gaps, unverified orders).
- Distinguishes evidence from assumption.
- Uses no guarantee-of-outcome language.

### FR-5.1.6 Inconclusive test detection
**User story:** As a merchant, I want inconclusive tests identified so I do not act on weak evidence.
**Acceptance criteria:**
- Flags insufficient traffic, spend, conversions, missing tracking, or unreliable attribution.
- States which specific condition triggered the inconclusive result.
- Routes the test to Extend Test rather than Go/No-Go.

### FR-5.1.7 Extend a test
**User story:** As a merchant, I want to extend an inconclusive test so I can gather more evidence.
**Acceptance criteria:**
- Merchant can extend with explicit additional budget and duration.
- Extension is validated against budget caps.
- The new window is recorded separately.
- Verdict is recomputed under a documented policy (combined or new-window data).
- Prior verdict and data snapshot remain in history.

---

## Module 5.2 — Predictive Batch Quantity and Investment Recommendation

### FR-5.2.1 Collect investment inputs
**User story:** As a store owner, I want to enter costs and budget so recommendations reflect my constraints.
**Acceptance criteria:**
- Collects unit cost, selling price, fulfillment/shipping, payment fees, available budget, target margin, supplier MOQ, and lead time.
- Values are range-validated and currency-consistent.
- Missing values are flagged explicitly, never silently defaulted.
- Inputs are saved per product/test.

### FR-5.2.2 Demand estimation with stated assumptions
**User story:** As a store owner, I want a demand estimate that explains its assumptions so I understand the risk.
**Acceptance criteria:**
- Converts test conversion data into a low/base/high demand range.
- Assumptions are explicit: traffic source, repeat rate, seasonality, and attribution adjustment.
- Confidence and limitations are displayed.
- No single-point certainty is presented.

### FR-5.2.3 Unit economics
**User story:** As a store owner, I want unit economics so I can judge profitability before ordering.
**Acceptance criteria:**
- Computes contribution margin per unit (price − COGS − fulfillment − fees).
- Computes break-even units and CAC from test spend and conversions.
- Formulas are displayed.
- Negative-margin scenarios are clearly flagged.

### FR-5.2.4 Compute feasible order quantities
**User story:** As a store owner, I want recommended quantities that respect my budget and supplier constraints.
**Acceptance criteria:**
- Proposes at least two scenarios (e.g., conservative, base, aggressive) when data is sufficient.
- Scenarios respect MOQ, budget, and the demand range.
- Infeasible scenarios are excluded with an explanation.
- If no scenario is feasible, the system explains why instead of returning a number.

### FR-5.2.5 Scenario presentation and risk
**User story:** As a store owner, I want to compare quantities so I understand the trade-off between risk and opportunity.
**Acceptance criteria:**
- Each scenario shows inventory cost, expected units sold, revenue range, profit range, and sell-through %.
- Overstock risk and stockout risk are highlighted per scenario.
- Estimates are labeled as projections, not guarantees.
- Assumptions are listed for each scenario.

### FR-5.2.6 Adjust assumptions and recalculate with versioning
**User story:** As a store owner, I want to change assumptions and recalculate so I can evaluate alternatives.
**Acceptance criteria:**
- Merchant can edit supported assumptions, costs, and budget.
- Recalculation produces a new version.
- Original and revised assumptions are visually distinguishable.
- Version history is retained and recommendations update accordingly.

---

## Cross-Cutting Acceptance Criteria (apply to every requirement)

- Authorization is enforced server-side on every endpoint.
- Validation exists on both client and server; errors are specific and actionable.
- No stack traces, secrets, or unnecessary PII appear in user-facing errors or logs.
- Timestamps are stored in UTC and displayed in the store timezone; money is stored in minor units with currency.
- Merchant-facing UI and generated pages support required languages and RTL layouts.
- Generated landing pages meet WCAG 2.1 AA baseline.
- PII is minimized, encrypted at rest/in transit, and collected only with required consent.
- External calls use rate limiting, retries with backoff, timeouts, and idempotency.
- Structured logs, metrics, and job IDs exist for all async workflows.
- Documented performance budgets: page generation P95 ≤ 5 minutes; dashboard queries P95 < 2 seconds.
- Test coverage includes unit, integration, tenant-isolation, and end-to-end tests for critical flows.

---

## Suggested Delivery Slices

| Slice | Contents | Depends on |
|---|---|---|
| **A — Foundation & onboarding** | FR-0.x, 1.1.1–1.1.5, 1.2.x | — |
| **B — Concept evaluation** | 2.1.x, integration import 1.1.6 | A (sales + profile data) |
| **C — Recommendations & assets** | 2.2.x, 3.1.x, 3.2.x | B (concepts), D1/D3 decisions |
| **D — Measurement** | 4.1.x | C (live pages and campaigns) |
| **E — Decision & investment** | 5.1.x, 5.2.x | D (test results) |
| **F — Optimization** | 4.2.1–4.2.5, then 4.2.6–4.2.7 | D + at least one complete test cycle |

**Recommended MVP cut:** A + B + C + D + E, with 4.2.5 recommendations only. Defer 4.2.6 (automated execution), payment-based deposit verification (D2), and multi-touch attribution.

### Explicitly deferred
Automated budget reallocation, real-time streaming optimization, multi-touch attribution, payment processing, inventory/warehouse sync, mobile apps, and multi-user collaboration beyond the defined roles.
