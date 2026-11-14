"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ApiError, apiFetch } from "@/lib/api";

const fieldClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900";

type Metric = {
  value: number;
  label: string;
  definition: string;
  is_sale: boolean;
};

type Rate = {
  numerator: number;
  denominator: number;
  value: number | null;
  display: string;
  definition: string;
  formula: string;
};

type MetricGroup = {
  product_id: string | null;
  product_name: string;
  campaign_id: string | null;
  campaign_name: string;
  metrics: Record<string, Metric>;
  rates: Record<string, Rate>;
};

type Dashboard = {
  timezone: string;
  range: {
    start: string;
    end: string;
    start_local: string;
    end_local: string;
  };
  freshness: {
    last_event_received_at: string | null;
    last_metric_snapshot_at: string | null;
    last_update: string | null;
  };
  totals: {
    metrics: Record<string, Metric>;
    rates: Record<string, Rate>;
  };
  groups: MetricGroup[];
  label_policy: {
    rule: string;
    verified_metrics: string[];
    intent_metrics: string[];
  };
};

const TIMEZONES = [
  "UTC",
  "Asia/Riyadh",
  "Asia/Dubai",
  "Africa/Cairo",
  "Europe/London",
  "America/New_York",
];

const METRIC_ORDER = [
  "visits",
  "whatsapp_clicks",
  "cod_submissions",
  "confirmed_deposits",
];

const RATE_ORDER = [
  "visit_to_whatsapp",
  "visit_to_cod",
  "whatsapp_to_cod",
  "cod_to_confirmed_deposit",
];

function localInput(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate(),
  )}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Could not load metrics.";
}

function MetricsTable({ metrics }: { metrics: Record<string, Metric> }) {
  return (
    <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {METRIC_ORDER.map((key) => {
        const metric = metrics[key];
        return (
          <div key={key} className="rounded-md bg-zinc-50 p-3">
            <p className="text-xs text-zinc-500">{metric.label}</p>
            <p className="mt-1 text-2xl font-semibold">{metric.value}</p>
            <p className="mt-1 text-xs text-zinc-500">{metric.definition}</p>
            {metric.is_sale ? (
              <p className="mt-1 text-xs font-medium text-emerald-700">موثّق</p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function RatesList({ rates }: { rates: Record<string, Rate> }) {
  return (
    <div className="mt-3 space-y-2">
      {RATE_ORDER.map((key) => {
        const rate = rates[key];
        return (
          <div key={key} className="rounded-md border border-zinc-200 p-3 text-sm">
            <p className="font-medium">
              {rate.numerator} / {rate.denominator} = {rate.display}
            </p>
            <p className="mt-1 text-xs text-zinc-500">
              {rate.formula} — {rate.definition}
            </p>
          </div>
        );
      })}
    </div>
  );
}

export default function MetricsPage() {
  const now = new Date();
  const [start, setStart] = useState(localInput(new Date(now.getTime() - 7 * 86400000)));
  const [end, setEnd] = useState(localInput(now));
  const [timezone, setTimezone] = useState("UTC");
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({ start, end, timezone });
    apiFetch<Dashboard>(`/metrics/dashboard?${params.toString()}`)
      .then((result) => {
        if (!active) return;
        setData(result);
        setError(null);
      })
      .catch((loadError) => {
        if (active) setError(errorMessage(loadError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [start, end, timezone, refreshKey]);

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold">مؤشرات التحويل</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Visits, WhatsApp intent clicks, COD submissions, and confirmed deposits
            by product and campaign.
          </p>
        </div>

        <form
          className="grid gap-3 rounded-lg border border-zinc-200 bg-white p-4 sm:grid-cols-2 lg:grid-cols-4"
          onSubmit={(event) => {
            event.preventDefault();
            setLoading(true);
            setRefreshKey((value) => value + 1);
          }}
        >
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
          <label className="text-sm">
            Timezone
            <select
              value={timezone}
              onChange={(event) => setTimezone(event.target.value)}
              className={fieldClass}
            >
              {TIMEZONES.map((zone) => (
                <option key={zone} value={zone}>
                  {zone}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            className="self-end rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white"
          >
            Apply
          </button>
        </form>

        {error ? (
          <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">
            {error}
          </p>
        ) : null}

        {loading ? (
          <p className="text-sm text-zinc-500">Loading metrics...</p>
        ) : null}

        {data ? (
          <>
            <section className="rounded-lg border border-zinc-200 bg-white p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold">الإجماليات</h2>
                  <p className="mt-1 text-xs text-zinc-500">
                    {data.range.start_local} to {data.range.end_local} ({data.timezone})
                  </p>
                </div>
                <div className="text-end text-sm text-zinc-600">
                  <p className="font-medium">حداثة البيانات</p>
                  <p>{data.freshness.last_update ?? "لا توجد بيانات في هذه الفترة"}</p>
                </div>
              </div>
              <MetricsTable metrics={data.totals.metrics} />
              <RatesList rates={data.totals.rates} />
            </section>

            {data.groups.length === 0 ? (
              <p className="rounded-lg border border-dashed border-zinc-300 p-5 text-sm text-zinc-500">
                No metrics in this range.
              </p>
            ) : (
              data.groups.map((group) => (
                <section
                  key={`${group.product_id}-${group.campaign_id}`}
                  className="rounded-lg border border-zinc-200 bg-white p-5"
                >
                  <h2 className="text-base font-semibold">
                    {group.product_name} · {group.campaign_name}
                  </h2>
                  <MetricsTable metrics={group.metrics} />
                  <RatesList rates={group.rates} />
                </section>
              ))
            )}

            <p className="text-xs text-zinc-500">{data.label_policy.rule}</p>
          </>
        ) : null}
      </div>
    </AppShell>
  );
}
