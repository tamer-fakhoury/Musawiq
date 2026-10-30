"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

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
  const [converting, setConverting] = useState<ProductIdea | null>(null);
  const [convertName, setConvertName] = useState("");
  const [convertDescription, setConvertDescription] = useState("");
  const [convertPrice, setConvertPrice] = useState("");
  const [convertCost, setConvertCost] = useState("");
  const [convertCurrency, setConvertCurrency] = useState("USD");
  const [convertConfirmed, setConvertConfirmed] = useState(false);

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
      const idempotencyKey =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : String(Date.now());
      const result = await apiFetch<{
        run_id: string;
        job_id: string;
        status: string;
      }>("/recommendations/generate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey,
        },
        body: JSON.stringify({ count }),
      });
      let latest: GenerationRun | null = null;
      for (let attempt = 0; attempt < 15; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        latest = await apiFetch<GenerationRun>(
          `/recommendations/runs/${result.run_id}`,
        );
        if (latest.status === "succeeded" || latest.status === "failed") {
          break;
        }
      }
      setNotice(
        latest
          ? `حالة التوليد: ${runStatusLabel(latest.status)}.`
          : "تم إرسال مهمة التوليد.",
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

  function startConvert(idea: ProductIdea) {
    setConverting(idea);
    setConvertName(idea.name);
    setConvertDescription(idea.description);
    setConvertPrice("");
    setConvertCost("");
    setConvertCurrency("USD");
    setConvertConfirmed(false);
    setError(null);
    setNotice(null);
  }

  async function submitConvert(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!converting) {
      return;
    }
    if (!convertConfirmed) {
      setError("يجب تأكيد التحويل أولاً.");
      return;
    }
    const price = Number(convertPrice);
    const cost = Number(convertCost);
    if (!Number.isFinite(price) || price <= 0) {
      setError("السعر يجب أن يكون أكبر من صفر.");
      return;
    }
    if (!Number.isFinite(cost) || cost < 0) {
      setError("التكلفة يجب ألا تكون سالبة.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const concept = await apiFetch<{ id: string }>(
        `/recommendations/ideas/${converting.id}/convert`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            confirm: true,
            name: convertName,
            description: convertDescription,
            price_minor: Math.round(price * 100),
            cost_minor: Math.round(cost * 100),
            currency: convertCurrency.trim().toUpperCase(),
          }),
        },
      );
      setNotice(`تم إنشاء المفهوم ${concept.id.slice(0, 8)}.`);
      setConverting(null);
      setConvertConfirmed(false);
      await loadData();
    } catch (convertError) {
      setError(errorMessage(convertError, "تعذر تحويل الفكرة."));
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

        {converting ? (
          <section className="rounded-lg border border-amber-300 bg-white p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold">
                  تحويل «{converting.name}» إلى مفهوم
                </h2>
                <p className="mt-1 text-xs text-zinc-500">
                  الفئة والنيتش مأخوذتان من الفكرة. السعر والتكلفة من إدخالك.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setConverting(null)}
                className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
              >
                إلغاء
              </button>
            </div>
            <form onSubmit={submitConvert} className="mt-4 grid gap-4 md:grid-cols-2">
              <div>
                <label className="block text-sm font-medium text-zinc-700" htmlFor="convert-name">
                  الاسم
                </label>
                <input
                  id="convert-name"
                  value={convertName}
                  onChange={(event) => setConvertName(event.target.value)}
                  required
                  className={fieldClass}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700" htmlFor="convert-description">
                  الوصف
                </label>
                <input
                  id="convert-description"
                  value={convertDescription}
                  onChange={(event) => setConvertDescription(event.target.value)}
                  required
                  className={fieldClass}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700" htmlFor="convert-price">
                  السعر
                </label>
                <input
                  id="convert-price"
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={convertPrice}
                  onChange={(event) => setConvertPrice(event.target.value)}
                  required
                  className={fieldClass}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700" htmlFor="convert-cost">
                  التكلفة
                </label>
                <input
                  id="convert-cost"
                  type="number"
                  min="0"
                  step="0.01"
                  value={convertCost}
                  onChange={(event) => setConvertCost(event.target.value)}
                  required
                  className={fieldClass}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700" htmlFor="convert-currency">
                  العملة
                </label>
                <input
                  id="convert-currency"
                  value={convertCurrency}
                  onChange={(event) => setConvertCurrency(event.target.value)}
                  maxLength={3}
                  dir="ltr"
                  className={fieldClass}
                />
              </div>
              <div className="flex flex-col justify-end gap-3">
                <label className="flex items-center gap-2 text-sm text-zinc-700">
                  <input
                    type="checkbox"
                    checked={convertConfirmed}
                    onChange={(event) => setConvertConfirmed(event.target.checked)}
                  />
                  أؤكد تحويل الفكرة إلى مسودة مفهوم
                </label>
                <button
                  type="submit"
                  disabled={busy || !convertConfirmed}
                  className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  {busy ? "جارٍ التحويل…" : "تأكيد التحويل"}
                </button>
              </div>
            </form>
          </section>
        ) : null}

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
                          {idea.state !== "converted" ? (
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => startConvert(idea)}
                              className="rounded-md bg-zinc-900 px-2 py-1 text-xs font-medium text-white"
                            >
                              تحويل إلى مفهوم
                            </button>
                          ) : null}
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
