"use client";

import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ApiError, apiFetch } from "@/lib/api";

const fieldClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900";

type InvestmentProfile = {
  id: string;
  test_id: string;
  version: number;
  unit_cost_minor: number;
  selling_price_minor: number;
  fulfillment_cost_minor: number;
  payment_fee_bp: number;
  available_budget_minor: number;
  target_margin_bp: number;
  supplier_moq: number;
  lead_time_days: number;
  currency: string;
  is_current: boolean;
};

type QuantityScenario = {
  id: string;
  label: string;
  quantity: number;
  inventory_cost_minor: number;
  expected_units_sold_low: number;
  expected_units_sold_high: number;
  revenue_low_minor: number;
  revenue_high_minor: number;
  profit_low_minor: number;
  profit_high_minor: number;
  sell_through_low: number;
  sell_through_high: number;
  overstock_risk: string;
  stockout_risk: string;
  is_feasible: boolean;
  infeasibility_reason: string | null;
  is_projection: boolean;
  projection_label: string;
  assumptions: string[];
  notes: string[];
};

type ScenarioResult = {
  demand_range: {
    low_units: number;
    base_units: number;
    high_units: number;
  };
  constraint_notes: string[];
  scenarios: QuantityScenario[];
  excluded_scenarios: QuantityScenario[];
  has_feasible: boolean;
  explanation: string | null;
};

type FieldErrors = Record<string, string>;

type FormState = {
  test_id: string;
  unit_cost_minor: string;
  selling_price_minor: string;
  fulfillment_cost_minor: string;
  payment_fee_bp: string;
  available_budget_minor: string;
  target_margin_bp: string;
  supplier_moq: string;
  lead_time_days: string;
  currency: string;
};

const INITIAL: FormState = {
  test_id: "",
  unit_cost_minor: "",
  selling_price_minor: "",
  fulfillment_cost_minor: "",
  payment_fee_bp: "",
  available_budget_minor: "",
  target_margin_bp: "",
  supplier_moq: "",
  lead_time_days: "",
  currency: "USD",
};

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Could not save profile.";
}

function errorFields(error: unknown): FieldErrors {
  if (error instanceof ApiError) {
    const value = (error as ApiError & { fields?: FieldErrors }).fields;
    if (value) return value;
  }
  return {};
}

const NUMBER_FIELDS: Array<[keyof FormState, string]> = [
  ["unit_cost_minor", "Unit cost (minor units)"],
  ["selling_price_minor", "Selling price (minor units)"],
  ["fulfillment_cost_minor", "Fulfillment/shipping (minor units)"],
  ["payment_fee_bp", "Payment fee (basis points)"],
  ["available_budget_minor", "Available budget (minor units)"],
  ["target_margin_bp", "Target margin (basis points)"],
  ["supplier_moq", "Supplier MOQ"],
  ["lead_time_days", "Lead time (days)"],
];

export default function InvestmentPage() {
  const [form, setForm] = useState<FormState>(INITIAL);
  const [profile, setProfile] = useState<InvestmentProfile | null>(null);
  const [history, setHistory] = useState<InvestmentProfile[]>([]);
  const [scenarioResult, setScenarioResult] = useState<ScenarioResult | null>(
    null,
  );
  const [fields, setFields] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function update(field: keyof FormState, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function loadHistory(testId: string) {
    try {
      setHistory(
        await apiFetch<InvestmentProfile[]>(
          `/tests/${encodeURIComponent(testId)}/investment-profiles`,
        ),
      );
    } catch {
      setHistory([]);
    }
  }

  async function save() {
    if (!form.test_id.trim()) {
      setError("Test ID is required.");
      return;
    }
    setBusy(true);
    setError(null);
    setFields({});
    const payload: Record<string, number | string> = {
      currency: form.currency.trim().toUpperCase(),
    };
    for (const [field] of NUMBER_FIELDS) {
      const value = form[field].trim();
      if (value) payload[field] = Number(value);
    }
    try {
      const saved = await apiFetch<InvestmentProfile>(
        `/tests/${encodeURIComponent(form.test_id.trim())}/investment-profile`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      setProfile(saved);
      await loadHistory(form.test_id.trim());
    } catch (saveError) {
      setProfile(null);
      setFields(errorFields(saveError));
      setError(errorMessage(saveError));
    } finally {
      setBusy(false);
    }
  }

  async function generateScenarios() {
    if (!form.test_id.trim()) {
      setError("Test ID is required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setScenarioResult(
        await apiFetch<ScenarioResult>(
          `/tests/${encodeURIComponent(form.test_id.trim())}/quantity-scenarios`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
          },
        ),
      );
    } catch (scenarioError) {
      setScenarioResult(null);
      setError(errorMessage(scenarioError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold">مدخلات الاستثمار</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Costs, pricing, fees, budget, and supplier constraints. Each save
            creates a new version; missing values are listed explicitly.
          </p>
        </div>

        <form
          className="grid gap-3 rounded-lg border border-zinc-200 bg-white p-4 sm:grid-cols-2 lg:grid-cols-3"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <label className="text-sm">
            Test ID
            <input
              value={form.test_id}
              onChange={(event) => update("test_id", event.target.value)}
              dir="ltr"
              className={fieldClass}
            />
          </label>
          <label className="text-sm">
            Currency
            <input
              value={form.currency}
              onChange={(event) => update("currency", event.target.value)}
              maxLength={3}
              dir="ltr"
              className={fieldClass}
            />
          </label>
          {NUMBER_FIELDS.map(([field, label]) => (
            <label key={field} className="text-sm">
              {label}
              <input
                type="number"
                min={0}
                value={form[field]}
                onChange={(event) => update(field, event.target.value)}
                className={fieldClass}
              />
              {fields[field] ? (
                <span className="mt-1 block text-xs text-red-700">
                  {fields[field]}
                </span>
              ) : null}
            </label>
          ))}
          <button
            type="submit"
            disabled={busy}
            className="self-end rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {busy ? "جارٍ الحفظ..." : "حفظ إصدار جديد"}
          </button>
        </form>

        {error ? (
          <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">
            {error}
          </p>
        ) : null}

        {profile ? (
          <section className="rounded-lg border border-zinc-200 bg-white p-5">
            <h2 className="text-base font-semibold">
              Current profile | version {profile.version}
            </h2>
            <p className="mt-1 text-sm text-zinc-600">
              {profile.currency} | unit cost {profile.unit_cost_minor} | price{" "}
              {profile.selling_price_minor} | budget {profile.available_budget_minor}
            </p>
            <button
              type="button"
              onClick={() => void generateScenarios()}
              disabled={busy}
              className="mt-3 rounded-md border border-zinc-300 px-3 py-2 text-sm disabled:opacity-50"
            >
              Generate quantity scenarios
            </button>
          </section>
        ) : null}

        {scenarioResult ? (
          <section className="rounded-lg border border-zinc-200 bg-white p-5">
            <h2 className="text-base font-semibold">سيناريوهات الكمية</h2>
            <p className="mt-1 text-sm text-zinc-600">
              Demand range: {scenarioResult.demand_range.low_units} /{" "}
              {scenarioResult.demand_range.base_units} /{" "}
              {scenarioResult.demand_range.high_units} units
            </p>
            {scenarioResult.constraint_notes.map((note) => (
              <p key={note} className="mt-1 text-xs text-zinc-500">
                {note}
              </p>
            ))}
            {scenarioResult.has_feasible ? (
              <div className="mt-3 grid gap-3 md:grid-cols-3">
                {scenarioResult.scenarios.map((scenario) => (
                  <div
                    key={scenario.id}
                    className="rounded-md border border-zinc-200 p-3 text-sm"
                  >
                    <p className="text-xs uppercase tracking-wide text-amber-700">
                      {scenario.projection_label}
                    </p>
                    <p className="font-semibold capitalize">{scenario.label}</p>
                    <p className="mt-1 text-2xl font-semibold">
                      {scenario.quantity} units
                    </p>
                    <dl className="mt-2 space-y-1 text-xs text-zinc-600">
                      <div>
                        <dt>Inventory cost (projection)</dt>
                        <dd>{scenario.inventory_cost_minor}</dd>
                      </div>
                      <div>
                        <dt>Expected units sold (projection)</dt>
                        <dd>
                          {scenario.expected_units_sold_low}-
                          {scenario.expected_units_sold_high}
                        </dd>
                      </div>
                      <div>
                        <dt>Revenue range (projection)</dt>
                        <dd>
                          {scenario.revenue_low_minor}-{scenario.revenue_high_minor}
                        </dd>
                      </div>
                      <div>
                        <dt>Profit range (projection)</dt>
                        <dd>
                          {scenario.profit_low_minor}-{scenario.profit_high_minor}
                        </dd>
                      </div>
                      <div>
                        <dt>Sell-through (projection)</dt>
                        <dd>
                          {(scenario.sell_through_low * 100).toFixed(1)}%-
                          {(scenario.sell_through_high * 100).toFixed(1)}%
                        </dd>
                      </div>
                      <div>
                        <dt>خطر التكدس</dt>
                        <dd className="font-medium">{scenario.overstock_risk}</dd>
                      </div>
                      <div>
                        <dt>خطر النفاد</dt>
                        <dd className="font-medium">{scenario.stockout_risk}</dd>
                      </div>
                    </dl>
                    <details className="mt-2 text-xs text-zinc-500">
                      <summary className="cursor-pointer">الافتراضات</summary>
                      <ul className="mt-1 list-disc ps-4">
                        {scenario.assumptions.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </details>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-3 rounded-md bg-amber-50 p-3 text-sm text-amber-800">
                {scenarioResult.explanation}
              </p>
            )}
          </section>
        ) : null}

        {history.length > 0 ? (
          <section className="rounded-lg border border-zinc-200 bg-white p-5">
            <h2 className="text-base font-semibold">سجل الإصدارات</h2>
            <ul className="mt-3 divide-y divide-zinc-200">
              {history.map((row) => (
                <li key={row.id} className="py-2 text-sm">
                  v{row.version} | {row.is_current ? "current" : "historical"} |{" "}
                  {row.currency} | unit cost {row.unit_cost_minor}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </AppShell>
  );
}
