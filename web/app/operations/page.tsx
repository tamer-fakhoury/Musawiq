"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ApiError, apiFetch } from "@/lib/api";

const fieldClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900";

type AiStatus = {
  available: boolean;
  provider: string;
  degraded: boolean;
  manual_fallback: string;
};

type AuditRow = {
  id: string;
  created_at: string;
  action: string;
  target_type: string;
  target_id: string | null;
  actor_user_id: string | null;
};

type Job = {
  id: string;
  state: string;
  job_type: string;
  attempts: number;
  last_updated: string | null;
  error: { code: string; message: string } | null;
};

type AttributionCoverage = {
  total_subjects: number;
  attributed_subjects: number;
  coverage_percentage: number;
  model: string;
  window_seconds: number;
  config_version: number;
};

function errorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

export default function OperationsPage() {
  const [ai, setAi] = useState<AiStatus | null>(null);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [coverage, setCoverage] = useState<AttributionCoverage | null>(null);
  const [jobId, setJobId] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      apiFetch<AiStatus>("/ai/status"),
      apiFetch<{ items: AuditRow[] }>("/audit-logs?limit=20"),
      apiFetch<Record<string, unknown>>("/store/profile"),
      apiFetch<AttributionCoverage>("/attribution/coverage"),
    ])
      .then(([aiData, auditData, profileData, coverageData]) => {
        if (!active) return;
        setAi(aiData);
        setAudit(auditData.items ?? []);
        setProfile(profileData);
        setCoverage(coverageData);
      })
      .catch((loadError) => {
        if (active) setError(errorMessage(loadError, "تعذر تحميل العمليات."));
      });
    return () => {
      active = false;
    };
  }, []);

  async function loadJob() {
    setError(null);
    try {
      setJob(await apiFetch<Job>(`/jobs/${jobId.trim()}`));
    } catch (jobError) {
      setJob(null);
      setError(errorMessage(jobError, "تعذر تحميل المهمة."));
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold">العمليات</h1>
          <p className="mt-1 text-sm text-zinc-500">
            حالة الذكاء الاصطناعي، سجل التدقيق، ملف المتجر، ومتابعة المهام.
          </p>
          <a href="/health" className="mt-2 inline-block text-sm text-blue-700 underline">
            فحص صحة API
          </a>
        </div>
        {error ? <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-base font-semibold">الذكاء الاصطناعي</h2>
          {ai ? (
            <p className="mt-2 text-sm text-zinc-700">
              {ai.provider} • {ai.available ? "متاح" : "غير متاح"} • {ai.degraded ? "وضع مخفض" : "عادي"}
            </p>
          ) : <p className="mt-2 text-sm text-zinc-500">جارٍ التحميل…</p>}
        </section>

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-base font-semibold">تغطية الإسناد</h2>
          {coverage ? (
            <div className="mt-2 space-y-1 text-sm text-zinc-700">
              <p className="text-2xl font-semibold text-zinc-950">
                {coverage.coverage_percentage.toFixed(2)}%
              </p>
              <p>
                {coverage.attributed_subjects} of {coverage.total_subjects} subjects
                attributed | {coverage.model} | {coverage.window_seconds}s window |
                config v{coverage.config_version}
              </p>
            </div>
          ) : (
            <p className="mt-2 text-sm text-zinc-500">Loading coverage...</p>
          )}
        </section>

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-base font-semibold">متابعة مهمة</h2>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <input value={jobId} onChange={(event) => setJobId(event.target.value)} placeholder="Job UUID" dir="ltr" className={fieldClass} />
            <button type="button" onClick={() => void loadJob()} className="rounded-md border border-zinc-300 px-3 py-2 text-sm">عرض</button>
          </div>
          {job ? (
            <p className="mt-3 text-sm text-zinc-700">
              {job.job_type} • {job.state} • محاولات {job.attempts}
              {job.error ? <span className="block text-red-700">{job.error.code}: {job.error.message}</span> : null}
            </p>
          ) : null}
        </section>

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-base font-semibold">سجل التدقيق</h2>
          <ul className="mt-3 divide-y divide-zinc-200">
            {audit.map((row) => (
              <li key={row.id} className="py-2 text-sm">
                {row.action} • {row.target_type} • {row.created_at.slice(0, 19)}
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-base font-semibold">ملف المتجر</h2>
          <pre className="mt-2 overflow-auto rounded bg-zinc-50 p-2 text-xs" dir="ltr">
            {JSON.stringify(profile, null, 2)}
          </pre>
        </section>
      </div>
    </AppShell>
  );
}
