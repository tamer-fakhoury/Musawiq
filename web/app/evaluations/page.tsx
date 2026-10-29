"use client";

import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ApiError, apiFetch } from "@/lib/api";
import type { Concept } from "@/lib/concepts";
import {
  confidenceLabel,
  factorSourceLabel,
  formatScore,
  type Evaluation,
  type Explanation,
} from "@/lib/evaluations";

const fieldClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export default function EvaluationsPage() {
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiFetch<Concept[]>("/product-concepts?limit=100")
      .then((data) => {
        if (active) {
          const items = Array.isArray(data) ? data : [];
          setConcepts(items);
          setSelectedId((current) => current || items[0]?.id || "");
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
  }, []);

  const runEvaluation = useCallback(async () => {
    if (!selectedId) {
      setError("اختر مفهوماً أولاً.");
      return;
    }
    setBusy(true);
    setError(null);
    setEvaluation(null);
    setExplanation(null);
    try {
      const result = await apiFetch<Evaluation>(
        `/product-concepts/${selectedId}/evaluations`,
        { method: "POST" },
      );
      setEvaluation(result);
      const explained = await apiFetch<Explanation>(
        `/evaluations/${result.id}/explanation`,
      );
      setExplanation(explained);
    } catch (runError) {
      setError(errorMessage(runError, "تعذر تقييم المفهوم."));
    } finally {
      setBusy(false);
    }
  }, [selectedId]);

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold">تقييم الجدوى</h1>
          <p className="mt-1 text-sm text-zinc-500">
            شغّل نموذج التقييم ثم راجع العوامل والقيود والثقة.
          </p>
        </div>

        {error ? (
          <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">
            {error}
          </p>
        ) : null}

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-64 flex-1">
              <label
                className="block text-sm font-medium text-zinc-700"
                htmlFor="concept"
              >
                المفهوم
              </label>
              <select
                id="concept"
                value={selectedId}
                onChange={(event) => {
                  setSelectedId(event.target.value);
                  setEvaluation(null);
                  setExplanation(null);
                }}
                className={fieldClass}
                disabled={loading}
              >
                {concepts.length === 0 ? (
                  <option value="">لا توجد مفاهيم</option>
                ) : null}
                {concepts.map((concept) => (
                  <option key={concept.id} value={concept.id}>
                    {concept.name}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="button"
              onClick={() => void runEvaluation()}
              disabled={busy || !selectedId}
              className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {busy ? "جارٍ التقييم…" : "تقييم"}
            </button>
          </div>
        </section>

        {evaluation && explanation ? (
          <div className="space-y-6">
            <section className="rounded-lg border border-zinc-200 bg-white p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm text-zinc-500">النتيجة</p>
                  <p className="mt-1 text-3xl font-semibold">
                    {formatScore(evaluation.score, evaluation.score_scale)}
                  </p>
                </div>
                <div className="text-sm text-zinc-600">
                  <p>الثقة: {confidenceLabel(evaluation.confidence)}</p>
                  <p>
                    الموثوقية: {evaluation.is_reliable ? "موثوق" : "غير موثوق"}
                  </p>
                  <p>إصدار النموذج: {evaluation.model_version}</p>
                </div>
              </div>
              <p className="mt-4 text-sm text-zinc-700">{explanation.summary}</p>
              {explanation.limitations.length > 0 ? (
                <div className="mt-4 rounded-md bg-amber-50 p-3 text-sm text-amber-800">
                  <p className="font-medium">القيود</p>
                  <ul className="mt-1 list-inside list-disc space-y-1">
                    {explanation.limitations.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </section>

            <div className="grid gap-6 xl:grid-cols-2">
              <section className="rounded-lg border border-zinc-200 bg-white p-5">
                <h2 className="text-base font-semibold">أعلى العوامل الإيجابية</h2>
                <FactorList factors={explanation.top_positive} />
              </section>
              <section className="rounded-lg border border-zinc-200 bg-white p-5">
                <h2 className="text-base font-semibold">أعلى العوامل السلبية</h2>
                <FactorList factors={explanation.top_negative} />
              </section>
            </div>

            <section className="rounded-lg border border-zinc-200 bg-white p-5">
              <h2 className="text-base font-semibold">كل العوامل</h2>
              <FactorList factors={explanation.factors} />
              <p className="mt-4 text-xs text-zinc-500">
                مقاس: {explanation.measured_inputs.join("، ") || "—"}
                {" • "}
                مستنتج: {explanation.inferred_inputs.join("، ") || "—"}
              </p>
            </section>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}

function FactorList({
  factors,
}: {
  factors: Explanation["top_positive"];
}) {
  if (factors.length === 0) {
    return <p className="mt-3 text-sm text-zinc-500">لا توجد عوامل.</p>;
  }
  return (
    <ul className="mt-3 space-y-3">
      {factors.map((factor) => (
        <li key={factor.factor_key} className="rounded-md bg-zinc-50 p-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-medium">{factor.factor_label}</p>
            <span className="text-xs text-zinc-600">
              {factor.contribution.toFixed(2)} • {factorSourceLabel(factor.evidence_label)}
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-600">{factor.explanation}</p>
        </li>
      ))}
    </ul>
  );
}
