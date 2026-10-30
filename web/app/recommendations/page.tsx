"use client";

import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ApiError, apiFetch } from "@/lib/api";
import {
  formatDate,
  ideaStateLabel,
  runStatusLabel,
  type GenerationRun,
  type ProductIdea,
} from "@/lib/recommendations";

const fieldClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export default function RecommendationsPage() {
  const [ideas, setIdeas] = useState<ProductIdea[]>([]);
  const [runs, setRuns] = useState<GenerationRun[]>([]);
  const [count, setCount] = useState(3);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    const [ideaData, runData] = await Promise.all([
      apiFetch<ProductIdea[]>("/recommendations/ideas?limit=100"),
      apiFetch<GenerationRun[]>("/recommendations/runs"),
    ]);
    return {
      ideas: Array.isArray(ideaData) ? ideaData : [],
      runs: Array.isArray(runData) ? runData : [],
    };
  }, []);

  const loadData = useCallback(async () => {
    const data = await fetchData();
    setIdeas(data.ideas);
    setRuns(data.runs);
  }, [fetchData]);

  useEffect(() => {
    let active = true;
    fetchData()
      .then((data) => {
        if (active) {
          setIdeas(data.ideas);
          setRuns(data.runs);
          setLoading(false);
        }
      })
      .catch((loadError) => {
        if (active) {
          setError(errorMessage(loadError, "تعذر تحميل التوصيات."));
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [fetchData]);

  async function generate() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await apiFetch<{
        run_id: string;
        job_id: string;
        status: string;
      }>("/recommendations/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ count }),
      });
      setNotice(
        `تم إرسال مهمة التوليد (${result.run_id.slice(0, 8)}). حدّث القائمة بعد انتهاء العامل.`,
      );
      await loadData();
    } catch (generateError) {
      setError(errorMessage(generateError, "تعذر بدء التوليد."));
    } finally {
      setBusy(false);
    }
  }

  async function updateIdea(
    ideaId: string,
    action: "save" | "dismiss" | "restore",
  ) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const init: RequestInit = { method: "POST" };
      if (action === "dismiss") {
        const reason = window.prompt("سبب الاستبعاد (اختياري)") ?? "";
        init.headers = { "Content-Type": "application/json" };
        init.body = JSON.stringify({ reason: reason.trim() || null });
      }
      await apiFetch<ProductIdea>(
        `/recommendations/ideas/${ideaId}/${action}`,
        init,
      );
      setNotice("تم تحديث حالة الفكرة.");
      await loadData();
    } catch (updateError) {
      setError(errorMessage(updateError, "تعذر تحديث حالة الفكرة."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold">التوصيات</h1>
          <p className="mt-1 text-sm text-zinc-500">
            أنشئ أفكاراً جديدة اعتماداً على النيتش والجمهور وتاريخ المبيعات.
          </p>
        </div>

        {error ? (
          <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">
            {error}
          </p>
        ) : null}
        {notice ? (
          <p role="status" className="rounded-md bg-green-50 p-3 text-sm text-green-700">
            {notice}
          </p>
        ) : null}

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label
                className="block text-sm font-medium text-zinc-700"
                htmlFor="idea-count"
              >
                عدد الأفكار
              </label>
              <input
                id="idea-count"
                type="number"
                min={1}
                max={10}
                value={count}
                onChange={(event) => setCount(Number(event.target.value))}
                className={fieldClass}
              />
            </div>
            <button
              type="button"
              disabled={busy}
              onClick={() => void generate()}
              className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {busy ? "جارٍ الإرسال…" : "توليد أفكار"}
            </button>
            <button
              type="button"
              onClick={() => void loadData()}
              className="rounded-md border border-zinc-300 px-3 py-2 text-sm"
            >
              تحديث
            </button>
          </div>
        </section>

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-base font-semibold">آخر عمليات التوليد</h2>
          {loading ? (
            <p className="mt-3 text-sm text-zinc-500">جارٍ التحميل…</p>
          ) : null}
          {!loading && runs.length === 0 ? (
            <p className="mt-3 text-sm text-zinc-500">لا توجد عمليات.</p>
          ) : null}
          {runs.length > 0 ? (
            <ul className="mt-3 divide-y divide-zinc-200">
              {runs.slice(0, 10).map((run) => (
                <li key={run.id} className="py-2 text-sm">
                  <span className="font-medium">{runStatusLabel(run.status)}</span>
                  {" • "}
                  طلب {run.requested_count} / عاد {run.returned_count}
                  {" • "}
                  {formatDate(run.created_at)}
                  {run.error_message ? (
                    <span className="block text-xs text-red-700">
                      {run.error_message}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </section>

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-base font-semibold">مكتبة الأفكار</h2>
          {!loading && ideas.length === 0 ? (
            <p className="mt-3 text-sm text-zinc-500">لا توجد أفكار بعد.</p>
          ) : null}
          {ideas.length > 0 ? (
            <ul className="mt-3 space-y-3">
              {ideas.map((idea) => (
                <li
                  key={idea.id}
                  className="rounded-md border border-zinc-200 p-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium">{idea.name}</p>
                      <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-700">
                        {ideaStateLabel(idea.state)}
                      </span>
                    </div>
                    <div className="flex gap-2">
                      {idea.state === "dismissed" ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void updateIdea(idea.id, "restore")}
                          className="rounded-md border border-zinc-300 px-2 py-1 text-xs"
                        >
                          استعادة
                        </button>
                      ) : (
                        <>
                          {idea.state !== "saved" && idea.state !== "converted" ? (
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => void updateIdea(idea.id, "save")}
                              className="rounded-md border border-zinc-300 px-2 py-1 text-xs"
                            >
                              حفظ
                            </button>
                          ) : null}
                          {idea.state !== "converted" ? (
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => void updateIdea(idea.id, "dismiss")}
                              className="rounded-md border border-red-200 px-2 py-1 text-xs text-red-700"
                            >
                              استبعاد
                            </button>
                          ) : null}
                        </>
                      )}
                    </div>
                  </div>
                  <p className="mt-1 text-sm text-zinc-600">
                    {idea.description}
                  </p>
                  <p className="mt-1 text-xs text-zinc-500">
                    {idea.rationale}
                  </p>
                  <div className="mt-3 space-y-2">
                    {idea.evidence.length === 0 ? (
                      <p className="text-xs text-zinc-500">لا يوجد دليل.</p>
                    ) : null}
                    {idea.evidence.map((evidence) => (
                      <div
                        key={evidence.id}
                        className={
                          evidence.evidence_type === "verified"
                            ? "rounded-md border border-green-200 bg-green-50 p-2"
                            : "rounded-md border border-amber-200 bg-amber-50 p-2"
                        }
                      >
                        <div className="flex flex-wrap items-center gap-2 text-xs">
                          <span
                            className={
                              evidence.evidence_type === "verified"
                                ? "font-medium text-green-800"
                                : "font-medium text-amber-800"
                            }
                          >
                            {evidence.label}
                          </span>
                          {evidence.is_stale ? (
                            <span className="rounded-full bg-red-100 px-2 py-0.5 text-red-700">
                              قديم
                            </span>
                          ) : null}
                          {evidence.source_name ? (
                            <span className="text-zinc-600">
                              {evidence.source_name}
                            </span>
                          ) : null}
                          {evidence.source_published_at ? (
                            <span className="text-zinc-500">
                              {formatDate(evidence.source_published_at)}
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-1 text-xs text-zinc-700">
                          {evidence.claim}
                        </p>
                        {evidence.source_url ? (
                          <a
                            href={evidence.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-1 inline-block text-xs text-blue-700 underline"
                          >
                            المصدر
                          </a>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      </div>
    </AppShell>
  );
}
