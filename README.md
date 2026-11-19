# Using Guide — Musawiq

## 1. What Musawiq is

Musawiq is an Arabic-first product-testing platform for e-commerce merchants.

It helps a merchant answer one practical question:

> “Should I sell this product, and what should I do next?”

Instead of guessing, Musawiq guides the merchant through a repeatable loop:

1. Define the store and audience.
2. Create a product concept.
3. Check whether enough data exists.
4. Evaluate the concept.
5. Prepare a landing page and ad campaign.
6. Run the test and collect signals.
7. Review the test result, verdict, and investment recommendation.
8. Improve and test again.

The product is built for evidence-based decisions, not guarantees. Missing data is shown explicitly, and the system distinguishes measured facts from AI-generated hypotheses.

---

## 2. Who it is for

| Role | Main use |
| --- | --- |
| Store owner | Decide what to sell, approve tests, review verdicts and investment quantities |
| Store manager | Prepare concepts, pages, campaigns, and daily test operations |
| Analyst | Read results, compare concepts, and inspect explanations |
| Platform administrator | Manage shared taxonomy and platform-level defaults |

The MVP assumes one store per owner. All store data is isolated per tenant.

---

## 3. Product outline

### Store and access
- Create an account and verify the email.
- Sign in securely.
- Create the store and select its default currency, language, timezone, and country.
- The store is the tenant boundary for all data.

### Taxonomy and audience
- Select categories and niches that describe the market.
- Define the target audience by location, age, gender, interests, and language.
- Capture customer feedback to inform recommendations.
- Keep audience profiles versioned so old evaluations remain explainable.

### Product concepts
- Create a candidate product with name, description, category, niche, price, cost, currency, and image.
- The system computes gross margin.
- Concepts can be edited while in draft, archived, compared, and selected.

### Data sufficiency
Before evaluation, the system checks whether the required inputs exist:
- sales history
- audience data
- cost and price data
- competitive or market data

If important inputs are missing, the result is marked insufficient instead of producing a misleading score.

### Evaluation and explanation
- Score the concept with a versioned scoring model.
- Show the factors that increased or decreased the score.
- Show confidence, limitations, and whether inputs were measured or inferred.
- A score can be unavailable. It is never silently replaced with zero.

### Recommendations
- Generate product ideas from the store’s niche, audience, sales history, and available market data.
- Each idea includes a rationale and evidence provenance.
- Ideas can be saved, dismissed, restored, or converted into a concept.
- Dismissed ideas are excluded from future recommendation deduplication.

### Landing page builder
- Start from a selected concept.
- Add product details, price, currency, images, language, and target market.
- Generate and edit Arabic copy.
- Choose an order method: WhatsApp or cash on delivery (COD).
- Preview desktop and mobile layouts.
- Validate the order channel and accessibility basics.
- Publish to a shareable public URL.
- Keep page versions so published snapshots remain stable.

### Campaign execution
- Create a test with a budget and time window.
- Create a campaign, ad sets, and ad variations.
- Generate or write ad copy.
- Attach tracking parameters and tracking links.
- Run pre-flight validation before publishing.
- Publish the campaign and record the publication attempt.
- The merchant stays in control; automated write-back is not part of the MVP.

### Measurement and attribution
- Capture visitor sessions, events, orders, and deposits.
- Track WhatsApp clicks, COD order submissions, and confirmed deposits.
- Attribute conversions to the correct test, campaign, ad set, and variation.
- Store metric snapshots for spend, impressions, clicks, conversions, and other campaign metrics.
- Show data freshness and numerator/denominator for rates.

### Verdict
- Freeze the test data into a result snapshot.
- Apply the active decision rule set.
- Produce a verdict:
  - **Go**
  - **No-Go**
  - **Extend Test**
- Show whether the test was conclusive, the main reason, limitations, and the rules that were applied.

### Investment recommendation
- Enter unit cost, selling price, fulfillment cost, payment fees, available budget, target margin, supplier MOQ, and lead time.
- Review a demand range with stated assumptions.
- Review unit economics: contribution margin, break-even units, and CAC.
- Review conservative, base, and aggressive quantity scenarios.
- Recalculate with new assumptions while keeping previous versions.

---

## 4. The complete journey

### Step 1 — Create an account and store
**Merchant does**
- Signs up with an email and password.
- Verifies the email.
- Signs in.
- Creates the store with name, currency, language, timezone, and country.

**System does**
- Creates the user and store.
- Makes the user the store owner.
- Starts the onboarding profile.

**Output**
- An authenticated session tied to one store.

---

### Step 2 — Describe the market
**Merchant does**
- Selects at least one category.
- Selects or creates niches.
- Defines the current audience profile and segments.
- Optionally adds customer feedback.

**System does**
- Stores the taxonomy and versioned audience profile.
- Links feedback to the store and profile.
- Makes the inputs available to sufficiency checks and recommendations.

**Output**
- A reusable market and audience definition.

---

### Step 3 — Create a product concept
**Merchant does**
- Enters the product name and description.
- Selects category and niche.
- Enters price and cost in the store currency.
- Uploads an optional product image.
- Saves the concept as a draft.

**System does**
- Validates required fields and money values.
- Computes gross margin.
- Stores the concept with a version and lifecycle status.

**Output**
- A draft concept ready for assessment.

---

### Step 4 — Run the sufficiency check
**Merchant does**
- Requests a sufficiency check for the concept.

**System does**
- Checks sales history, audience, cost/price, and competitive data.
- Marks each input as available, missing, stale, or insufficient.
- Produces an overall sufficient/insufficient result with blocking reasons.

**Output**
- A clear list of what is missing before the merchant can trust an evaluation.

---

### Step 5 — Evaluate the concept
**Merchant does**
- Runs an evaluation, or a batch evaluation for several concepts.

**System does**
- Selects the active scoring model.
- Calculates the score and scale.
- Creates score factors with direction and contribution.
- Records confidence, reliability, input snapshot, and sufficiency reference.
- Produces an explanation of the strongest positive and negative factors.
- Labels inputs as measured or inferred where applicable.

**Output**
- A scored, explainable evaluation for the concept.

---

### Step 6 — Compare and select
**Merchant does**
- Compares concepts side by side.
- Reviews scores, factors, confidence, and margins.
- Selects the concept to test.

**System does**
- Ranks and compares selected concepts.
- Marks the chosen concept as selected.
- Prepares the handoff to the landing-page and test workflow.

**Output**
- One concept promoted into execution.

---

### Step 7 — Build the landing page
**Merchant does**
- Starts a landing page from the selected concept.
- Reviews product details and uploaded image.
- Generates Arabic copy and edits it if needed.
- Chooses WhatsApp or COD.
- Configures the number, message template, or COD form fields.
- Previews mobile and desktop layouts.
- Publishes the page.

**System does**
- Creates draft page versions.
- Generates copy through the configured AI provider.
- Validates forbidden claims and required fields.
- Verifies the order channel.
- Runs accessibility checks.
- Publishes a stable version and records the public URL.

**Output**
- A live product page ready to receive traffic.

---

### Step 8 — Prepare the campaign
**Merchant does**
- Creates a test with budget and dates.
- Creates a campaign and ad sets.
- Creates or generates ad variations.
- Approves the variations to run.
- Generates tracking links.
- Runs pre-flight checks.
- Publishes the campaign.

**System does**
- Validates budget, targeting, destination, and tracking.
- Checks that a valid ad account connection and order channel exist.
- Records publication attempts and external references.
- Preserves the campaign configuration used for the test.

**Output**
- A running campaign pointed at the landing page and tracked for attribution.

---

### Step 9 — Run the test and collect signals
**Merchant does**
- Monitors spend, visits, clicks, orders, and deposits.
- Ingests or submits metric windows and events.

**System does**
- Stores raw and normalized metric snapshots.
- Records events and orders with attribution.
- Calculates rates with explicit numerators and denominators.
- Shows freshness and missing-data warnings.

**Output**
- A reliable measurement window for the test.

---

### Step 10 — Receive the test result
**Merchant does**
- Opens the test result when the window closes.
- Reviews the snapshot and verdict.
- Reads the primary reason and limitations.

**System does**
- Freezes the result snapshot.
- Applies the active decision rule set.
- Produces **Go**, **No-Go**, or **Extend Test**.
- Explains which thresholds were met or missed.
- Keeps the rule version and input references for auditability.

**Output**
- A defensible test result, not just a raw number.

---

### Step 11 — Decide the next investment step
**Merchant does**
- Opens the investment recommendation.
- Reviews demand range, unit economics, and quantity scenarios.
- Adjusts assumptions and recalculates when needed.

**System does**
- Estimates low/base/high demand with explicit assumptions.
- Calculates contribution margin, break-even units, and CAC.
- Produces feasible quantity scenarios with overstock and stockout risk.
- Keeps previous recommendation versions intact.

**Output**
- A practical answer to “how much should I order, and what is the risk?”

---

### Step 12 — Learn and repeat
**Merchant does**
- Applies the learned changes to the product page, offer, audience, or campaign.
- Starts a new test or a re-evaluation.

**System does**
- Keeps previous evaluations, analyses, versions, and verdicts.
- Compares before/after results when a parent analysis exists.
- Prevents silent history changes.

**Output**
- A repeatable improvement loop.

---

## 5. What “test results” includes

A completed test can return:

| Result area | What the merchant sees |
| --- | --- |
| Snapshot | Spend, impressions, clicks, conversions, deposits, conversion rate, cost per conversion, data completeness |
| Verdict | Go, No-Go, or Extend Test |
| Explanation | Main reason, met/missed thresholds, limitations, rule trace |
| Attribution | Which campaign, ad set, ad variation, page, or post received credit |
| Data quality | Freshness, missing periods, and confidence |
| Next action | Continue, stop, extend, adjust, or recalculate investment |

---

## 6. Status lifecycle at a glance

### Product concept
`draft` → `evaluated` → `selected` → `archived`

### Landing page
`draft` → `published` → `unpublished`

### Campaign
`draft` → `submitted` → `active` → `paused` → `completed`
Failure paths: `rejected`, `failed`

### Test
`draft` → `running` → `awaiting_verdict` → `completed`
Alternative paths: `paused`, `extended`, `cancelled`

### Verdict
`go` | `no_go` | `extend_test`

---

## 7. Working principles

1. **No fabrication.** Missing data is shown as missing; AI output is not presented as measured fact.
2. **Explainability.** Every score and verdict must show its factors, rules, or limitations.
3. **Merchant control.** Recommendations are advisory; the merchant applies changes.
4. **Auditability.** Evaluations, versions, verdicts, and recommendations keep their inputs and history.
5. **Tenant isolation.** Every store only sees its own data.
6. **Arabic-first.** The interface and generated copy support Arabic RTL, while identifiers such as email, phone, URLs, and codes remain LTR.
7. **Clear status.** Empty, loading, success, warning, and failure states must tell the merchant what happened and what to do next.

---

## 8. Recommended first-run checklist

- [ ] Create account and verify email
- [ ] Sign in and create store
- [ ] Select categories and niches
- [ ] Define the first audience profile
- [ ] Create the first product concept
- [ ] Run sufficiency check
- [ ] Run evaluation and read the explanation
- [ ] Select the concept
- [ ] Create and publish the landing page
- [ ] Configure and publish the campaign
- [ ] Collect the test window
- [ ] Review the verdict and test result
- [ ] Review the investment recommendation
- [ ] Apply changes and run the next test

---

## 9. Current product boundaries

- No automatic campaign optimization or write-back to ad platforms in the MVP.
- No payment-gateway webhook path for deposits; manual verification is supported.
- No multi-touch attribution; the MVP uses a single-touch model.
- No multi-store membership model; the MVP assumes one store per owner.
- No currency conversion; the selected currency is the store’s reporting currency.
- AI output is advisory and must pass schema and evidence validation before use.

---

## 10. Short summary

Musawiq turns product guessing into a traceable testing process:

**Idea → concept → sufficiency → evaluation → landing page → campaign → signals → test result → verdict → investment decision → next test.**
