"use client";

import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ApiError, apiFetch } from "@/lib/api";
import type { Concept } from "@/lib/concepts";
import {
  type ComparisonConcept,
  type ComparisonResult,
  type SelectionResult,
} from "@/lib/comparison";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function scoreLabel(concept: ComparisonConcept): string {
  return concept.score === null
    ? "غير متاح"
    : `${concept.score.toFixed(1)} / ${concept.score_scale}`;
}

export default function ComparePage() {
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const fetchConcepts = useCallback(async () => {
    const data = await apiFetch<Concept[]>("/product-concepts?limit=100");
    return (Array.isArray(data) ? data : []).filter(
      (concept) =>
        concept.status === "evaluated" || concept.status === "selected",
    );
  }, []);

  const loadConcepts = useCallback(async () => {
    const items = await fetchConcepts();
    setConcepts(items);
    return items;
  }, [fetchConcepts]);

  useEffect(() => {
    let active = true;
    fetchConcepts()
      .then((items) => {
        if (active) {
          setConcepts(items);
          setLoading(false);
        }
      })
      .catch((loadError) => {
        if (active) {
          setError(errorMessage(loadError, "تعذر تحميل المفاهيم."));
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [fetchConcepts]);

  function toggle(conceptId: string) {
    setSelected((current) =>
      current.includes(conceptId)
        ? current.filter((item) => item !== conceptId)
        : [...current, conceptId],
    );
  }

  async function compare() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await apiFetch<ComparisonResult>(
        "/product-concepts/compare",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ concept_ids: selected }),
        },
      );
      setComparison(result);
    } catch (compareError) {
      setError(errorMessage(compareError, "تعذر مقارنة المفاهيم."));
    } finally {
      setBusy(false);
    }
  }

  async function select() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await apiFetch<SelectionResult>(
        "/product-concepts/select",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ concept_ids: selected }),
        },
      );
      setNotice(
        `تم اختيار ${result.selected_ids.length} مفهوم للانتقال إلى المرحلة الثانية.`,
      );
      setComparison(null);
      setSelected([]);
      await loadConcepts();
    } catch (selectError) {
      setError(errorMessage(selectError, "تعذر اختيار المفاهيم."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold">مقارنة المفاهيم</h1>
          <p className="mt-1 text-sm text-zinc-500">
            اختر مفهومين أو أكثر من المفاهيم المقيّمة ثم قارن الدرجات
            والعوامل.
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
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-semibold">المفاهيم المتاحة</h2>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={busy || selected.length < 2}
                onClick={() => void compare()}
                className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm disabled:opacity-50"
              >
                مقارنة
              </button>
              <button
                type="button"
                disabled={busy || selected.length === 0}
                onClick={() => void select()}
                className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                اختيار للمرحلة الثانية
              </button>
            </div>
          </div>

          {loading ? (
            <p className="mt-4 text-sm text-zinc-500">جارٍ التحميل…</p>
          ) : null}
          {!loading && concepts.length === 0 ? (
            <p className="mt-4 text-sm text-zinc-500">
              لا توجد مفاهيم مقيّمة بعد.
            </p>
          ) : null}
          {!loading && concepts.length > 0 ? (
            <ul className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {concepts.map((concept) => (
                <li
                  key={concept.id}
                  className="rounded-md border border-zinc-200 p-3"
                >
                  <label className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      checked={selected.includes(concept.id)}
                      onChange={() => toggle(concept.id)}
                      className="mt-1"
                    />
                    <span>
                      <span className="block text-sm font-medium">
                        {concept.name}
                      </span>
                      <span className="mt-1 block text-xs text-zinc-500">
                        {concept.status === "selected"
                          ? "مختار"
                          : "تم التقييم"}
                        {" • "}
                        {concept.latest_score === null
                          ? "درجة غير متاحة"
                          : `الدرجة ${concept.latest_score.toFixed(1)}`}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          ) : null}
        </section>

        {comparison ? (
          <section className="rounded-lg border border-zinc-200 bg-white p-5">
            <h2 className="text-base font-semibold">النتيجة</h2>
            <div className="mt-4 grid gap-4 xl:grid-cols-2">
              {comparison.concepts.map((concept) => (
                <article
                  key={concept.concept_id}
                  className="rounded-md border border-zinc-200 p-4"
                >
                  <h3 className="font-medium">{concept.name}</h3>
                  <p className="mt-1 text-sm text-zinc-600">
                    الدرجة: {scoreLabel(concept)}
                    {" • "}
                    الثقة: {concept.confidence}
                  </p>
                  <p className="mt-1 text-xs text-zinc-500">
                    {concept.category ?? "بدون فئة"}
                    {" • "}
                    {(concept.price_minor / 100).toFixed(2)}{" "}
                    {concept.currency}
                    {" • "}
                    هامش {concept.gross_margin_percent.toFixed(1)}%
                  </p>
                  <ul className="mt-3 space-y-2">
                    {concept.top_factors.map((factor) => (
                      <li
                        key={factor.factor_key}
                        className="rounded bg-zinc-50 p-2 text-xs"
                      >
                        <span className="font-medium">
                          {factor.factor_label}
                        </span>
                        {" • "}
                        {factor.contribution.toFixed(2)}
                        {" • "}
                        {factor.direction}
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </AppShell>
  );
}
