"use client";

import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ApiError, apiFetch } from "@/lib/api";

const fieldClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900";

type Kpi = {
  value?: number | null;
  value_minor?: number | null;
  numerator?: number | null;
  denominator?: number | null;
  formula: string;
  definition: string;
  display: string;
  available: boolean;
  currency?: string;
};

type Snapshot = {
  test_id: string;
  currency: string;
  spend_minor: number;
  clicks: number;
  tracked_conversions: number;
  confirmed_deposits: number;
  primary_conversion: string;
  primary_conversion_event: string | null;
  kpis: Record<string, Kpi>;
  warnings: string[];
};

type Threshold = {
  key: string;
  label: string;
  threshold: unknown;
  observed: unknown;
  status: "met" | "missed";
};

type Limitation = {
  code: string;
  label: string;
  detail: string;
};

type SourceItem = {
  label: "evidence" | "assumption";
  source: string;
  detail: string;
};

type Explanation = {
  verdict_id: string;
  outcome: string;
  is_conclusive: boolean;
  summary: string;
  key_metrics: Array<{ key: string; label: string; display: string }>;
  thresholds: Threshold[];
  limitations: Limitation[];
  evidence: SourceItem[];
  assumptions: SourceItem[];
  attribution_coverage: { display: string; threshold: number };
  copy_guardrails: { checked: boolean; policy: string };
};

const KPI_ORDER = [
  "total_spend",
  "conversion_rate",
  "cost_per_conversion",
  "cost_per_confirmed_deposit",
];

const KPI_LABELS: Record<string, string> = {
  total_spend: "Total spend",
  conversion_rate: "Conversion rate",
  cost_per_conversion: "Cost per tracked conversion",
  cost_per_confirmed_deposit: "Cost per confirmed deposit",
};

function localInput(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate(),
  )}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Could not load snapshot.";
}

export default function VerdictsPage() {
  const now = new Date();
  const [testId, setTestId] = useState("");
  const [start, setStart] = useState(
    localInput(new Date(now.getTime() - 7 * 86400000)),
  );
  const [end, setEnd] = useState(localInput(now));
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [verdictBusy, setVerdictBusy] = useState(false);

  async function load() {
    if (!testId.trim()) {
      setError("Test ID is required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setSnapshot(
        await apiFetch<Snapshot>(
          `/tests/${encodeURIComponent(testId.trim())}/result-snapshots`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              period_start: start,
              period_end: end,
            }),
          },
        ),
      );
    } catch (loadError) {
      setSnapshot(null);
      setExplanation(null);
      setError(errorMessage(loadError));
    } finally {
      setBusy(false);
    }
  }

  async function evaluate() {
    if (!testId.trim()) {
      setError("Test ID is required.");
      return;
    }
    setVerdictBusy(true);
    setError(null);
    try {
      const verdict = await apiFetch<{ id: string }>(
        `/tests/${encodeURIComponent(testId.trim())}/verdicts`,
        { method: "POST" },
      );
      setExplanation(
        await apiFetch<Explanation>(`/verdicts/${verdict.id}/explanation`),
      );
    } catch (loadError) {
      setExplanation(null);
      setError(errorMessage(loadError));
    } finally {
      setVerdictBusy(false);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold">مؤشرات الحكم</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Snapshot KPIs with explicit formulas, denominators, and N/A semantics.
          </p>
        </div>

        <form
          className="grid gap-3 rounded-lg border border-zinc-200 bg-white p-4 sm:grid-cols-2 lg:grid-cols-4"
          onSubmit={(event) => {
            event.preventDefault();
            void load();
          }}
        >
          <label className="text-sm">
            Test ID
            <input
              value={testId}
              onChange={(event) => setTestId(event.target.value)}
              dir="ltr"
              className={fieldClass}
            />
          </label>
          <label className="text-sm">
            Start
            <input
              type="datetime-local"
              value={start}
              onChange={(event) => setStart(event.target.value)}
              className={fieldClass}
            />
          </label>
          <label className="text-sm">
            End
            <input
              type="datetime-local"
              value={end}
              onChange={(event) => setEnd(event.target.value)}
              className={fieldClass}
            />
          </label>
          <button
            type="submit"
            disabled={busy}
            className="self-end rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {busy ? "Calculating..." : "Calculate"}
          </button>
        </form>

        {error ? (
          <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">
            {error}
          </p>
        ) : null}

        {snapshot ? (
          <>
            <section className="rounded-lg border border-zinc-200 bg-white p-5">
              <h2 className="text-base font-semibold">اللقطة</h2>
              <p className="mt-1 text-sm text-zinc-600">
                Primary conversion: {snapshot.primary_conversion}
                {snapshot.primary_conversion_event
                  ? ` (${snapshot.primary_conversion_event})`
                  : ""}
                {" | "}
                {snapshot.clicks} clicks | {snapshot.tracked_conversions} tracked
                conversions | {snapshot.confirmed_deposits} confirmed deposits
              </p>
              {snapshot.warnings.length > 0 ? (
                <ul className="mt-2 list-disc ps-5 text-sm text-amber-700">
                  {snapshot.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              ) : null}
              <button
                type="button"
                onClick={() => void evaluate()}
                disabled={verdictBusy}
                className="mt-3 rounded-md border border-zinc-300 px-3 py-2 text-sm disabled:opacity-50"
              >
                {verdictBusy ? "Evaluating..." : "Evaluate verdict"}
              </button>
            </section>

            <div className="grid gap-3 md:grid-cols-2">
              {KPI_ORDER.map((key) => {
                const kpi = snapshot.kpis[key];
                return (
                  <section
                    key={key}
                    className="rounded-lg border border-zinc-200 bg-white p-5"
                  >
                    <h2 className="text-base font-semibold">{KPI_LABELS[key]}</h2>
                    <p className="mt-2 text-2xl font-semibold">{kpi.display}</p>
                    <p className="mt-2 text-sm text-zinc-600">
                      {kpi.numerator ?? "N/A"} / {kpi.denominator ?? "N/A"}
                    </p>
                    <p className="mt-1 font-mono text-xs text-zinc-500">
                      {kpi.formula}
                    </p>
                    <p className="mt-1 text-xs text-zinc-500">{kpi.definition}</p>
                  </section>
                );
              })}
            </div>

            {explanation ? (
              <>
                <section className="rounded-lg border border-zinc-200 bg-white p-5">
                  <h2 className="text-base font-semibold">
                    Verdict explanation: {explanation.outcome}
                  </h2>
                  <p className="mt-1 text-sm text-zinc-600">
                    {explanation.summary}
                  </p>
                  <p className="mt-2 text-xs text-zinc-500">
                    Attribution coverage: {explanation.attribution_coverage.display}
                    {" | "}
                    {explanation.is_conclusive ? "conclusive" : "inconclusive"}
                  </p>
                </section>

                <section className="rounded-lg border border-zinc-200 bg-white p-5">
                  <h2 className="text-base font-semibold">المؤشرات الرئيسية</h2>
                  <ul className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {explanation.key_metrics.map((metric) => (
                      <li key={metric.key} className="rounded-md bg-zinc-50 p-3">
                        <p className="text-xs text-zinc-500">{metric.label}</p>
                        <p className="mt-1 text-lg font-semibold">{metric.display}</p>
                      </li>
                    ))}
                  </ul>
                </section>

                <section className="rounded-lg border border-zinc-200 bg-white p-5">
                  <h2 className="text-base font-semibold">الحدود</h2>
                  <ul className="mt-3 divide-y divide-zinc-200">
                    {explanation.thresholds.map((threshold) => (
                      <li
                        key={threshold.key}
                        className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
                      >
                        <span>{threshold.label}</span>
                        <span dir="ltr" className="text-xs text-zinc-500">
                          observed {String(threshold.observed)} / threshold{" "}
                          {String(threshold.threshold)}
                        </span>
                        <span
                          className={
                            threshold.status === "met"
                              ? "font-medium text-emerald-700"
                              : "font-medium text-red-700"
                          }
                        >
                          {threshold.status}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>

                <section className="rounded-lg border border-zinc-200 bg-white p-5">
                  <h2 className="text-base font-semibold">قيود البيانات</h2>
                  <ul className="mt-3 space-y-2 text-sm">
                    {explanation.limitations.map((limitation) => (
                      <li key={`${limitation.code}-${limitation.detail}`}>
                        <span className="font-medium">{limitation.label}:</span>{" "}
                        {limitation.detail}
                      </li>
                    ))}
                  </ul>
                </section>

                <div className="grid gap-3 md:grid-cols-2">
                  <section className="rounded-lg border border-zinc-200 bg-white p-5">
                    <h2 className="text-base font-semibold">الأدلة</h2>
                    <ul className="mt-3 space-y-2 text-sm">
                      {explanation.evidence.length === 0 ? (
                        <li className="text-zinc-500">No direct evidence in range.</li>
                      ) : (
                        explanation.evidence.map((item) => (
                          <li key={item.source}>
                            <span className="font-medium">{item.source}:</span>{" "}
                            {item.detail}
                          </li>
                        ))
                      )}
                    </ul>
                  </section>
                  <section className="rounded-lg border border-zinc-200 bg-white p-5">
                    <h2 className="text-base font-semibold">الافتراضات</h2>
                    <ul className="mt-3 space-y-2 text-sm">
                      {explanation.assumptions.map((item) => (
                        <li key={item.source}>
                          <span className="font-medium">{item.source}:</span>{" "}
                          {item.detail}
                        </li>
                      ))}
                    </ul>
                  </section>
                </div>

                <p className="text-xs text-zinc-500">
                  {explanation.copy_guardrails.policy}
                </p>
              </>
            ) : null}
          </>
        ) : null}
      </div>
    </AppShell>
  );
}
