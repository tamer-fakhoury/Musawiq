"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ApiError, apiFetch } from "@/lib/api";
import {
  ACTION_LABELS,
  DEMAND_LABELS,
  DEMAND_STYLES,
  ISSUE_TYPE_LABELS,
  ISSUE_TYPE_ORDER,
  SEVERITY_LABELS,
  SEVERITY_STYLES,
  STATUS_LABELS,
  confidencePercent,
  failureMessage,
  isAnalysisResult,
  type Analysis,
  type AnalysisSummary,
} from "@/lib/analyses";
import { formatDate, type CopyVariant } from "@/lib/campaigns";

const cardClass = "rounded-lg border border-zinc-200 bg-white p-5";
const secondaryButtonClass =
  "rounded-md border border-zinc-300 px-3 py-1.5 text-sm text-zinc-700 disabled:opacity-50";

type CopyHandler = (key: string, text: string) => void;

export default function CampaignAnalysisPage() {
  const params = useParams<{ id: string }>();
  const campaignId = params.id;

  const [history, setHistory] = useState<AnalysisSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState(false);

  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [notAvailable, setNotAvailable] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const [variants, setVariants] = useState<CopyVariant[]>([]);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestError, setSuggestError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiFetch<AnalysisSummary[]>(`/campaigns/${campaignId}/analyses`)
      .then((data) => {
        if (active) {
          setHistory(Array.isArray(data) ? data : []);
        }
      })
      .catch((error) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 404) {
          setNotAvailable(true);
        } else {
          setHistoryError(true);
        }
      })
      .finally(() => {
        if (active) {
          setHistoryLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [campaignId]);

  const refreshHistory = useCallback(async () => {
    try {
      const data = await apiFetch<AnalysisSummary[]>(
        `/campaigns/${campaignId}/analyses`,
      );
      setHistory(Array.isArray(data) ? data : []);
    } catch {
      // The new analysis is already on screen; the list is best-effort.
    }
  }, [campaignId]);

  async function runAnalysis() {
    setRunning(true);
    setRunError(null);
    setNotAvailable(false);
    try {
      const created = await apiFetch<Analysis>(
        `/campaigns/${campaignId}/analyses`,
        { method: "POST" },
      );
      setAnalysis(created);
      await refreshHistory();
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 429) {
          setRunError(
            "تم تجاوز الحد المسموح من التحليلات. حاول مرة أخرى بعد قليل.",
          );
        } else if (error.status === 503) {
          setRunError("خدمة التحليل غير متاحة مؤقتاً. حاول لاحقاً.");
        } else if (error.status === 404) {
          setNotAvailable(true);
        } else {
          setRunError("تعذّر تشغيل التحليل. حاول مرة أخرى.");
        }
      } else {
        setRunError("تعذّر تشغيل التحليل. حاول مرة أخرى.");
      }
    } finally {
      setRunning(false);
    }
  }

  async function openAnalysis(id: string) {
    setLoadingId(id);
    setRunError(null);
    try {
      setAnalysis(await apiFetch<Analysis>(`/analyses/${id}`));
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setNotAvailable(true);
      } else {
        setRunError("تعذّر تحميل التحليل المحدد.");
      }
    } finally {
      setLoadingId(null);
    }
  }

  async function copy(key: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
    } catch {
      setRunError("تعذّر النسخ إلى الحافظة.");
    }
  }

  async function suggestCopy() {
    setSuggesting(true);
    setSuggestError(null);
    try {
      const data = await apiFetch<{ variants: CopyVariant[] }>(
        `/campaigns/${campaignId}/variations/suggest`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ count: 3 }),
        },
      );
      setVariants(Array.isArray(data.variants) ? data.variants : []);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 429) {
          setSuggestError(
            "تم تجاوز الحد المسموح من الاقتراحات. حاول مرة أخرى بعد قليل.",
          );
        } else if (error.status === 503) {
          setSuggestError(
            "مزوّد الذكاء الاصطناعي غير متاح حالياً، لذلك لم تُنتج اقتراحات.",
          );
        } else if (error.status === 502) {
          setSuggestError("تعذّر توليد نصوص صالحة. حاول مرة أخرى.");
        } else if (error.status === 404) {
          setSuggestError("الحملة غير موجودة.");
        } else {
          setSuggestError("تعذّر توليد النصوص. حاول مرة أخرى.");
        }
      } else {
        setSuggestError("تعذّر توليد النصوص. حاول مرة أخرى.");
      }
    } finally {
      setSuggesting(false);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">تحليل الإشارات</h1>
            <p className="mt-1 text-sm text-zinc-500">
              شغّل تشخيص الذكاء الاصطناعي واطّلع على التحليلات السابقة.
            </p>
          </div>
          <Link href="/campaigns" className={secondaryButtonClass}>
            العودة إلى الحملات
          </Link>
        </div>

        <section className={cardClass}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold">تشخيص جديد</h2>
              <p className="mt-1 text-sm text-zinc-500">
                يستخدم التحليل آخر سبعة أيام من الإشارات المسجّلة.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void runAnalysis()}
              disabled={running}
              className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {running ? "جارٍ التحليل…" : "تشغيل التحليل"}
            </button>
          </div>
          {running ? (
            <p role="status" className="mt-3 text-sm text-zinc-600">
              قد يستغرق التحليل عدة ثوانٍ. لا تغلق الصفحة.
            </p>
          ) : null}
          {notAvailable ? (
            <div
              role="status"
              className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
            >
              ميزة التحليل غير متاحة بعد. سيُفعّل هذا المسار في تحديث لاحق.
            </div>
          ) : null}
          {runError ? (
            <p role="alert" className="mt-3 text-sm text-red-700">
              {runError}
            </p>
          ) : null}
        </section>

        {analysis ? (
          <AnalysisView
            analysis={analysis}
            copiedKey={copiedKey}
            onCopy={copy}
          />
        ) : (
          <p className="text-sm text-zinc-500">
            لم يتم اختيار تحليل بعد. شغّل تحليلاً جديداً أو اختر تحليلاً سابقاً.
          </p>
        )}

        <section className={cardClass}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold">اقترح نصوصاً جديدة</h2>
              <p className="mt-1 text-sm text-zinc-500">
                ثلاثة نصوص بديلة للمراجعة اليدوية. لا تُحفظ الاقتراحات.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void suggestCopy()}
              disabled={suggesting}
              className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {suggesting ? "جارٍ التوليد…" : "اقترح نصوصاً"}
            </button>
          </div>
          {suggesting ? (
            <p role="status" className="mt-3 text-sm text-zinc-600">
              قد يستغرق توليد النصوص عدة ثوانٍ.
            </p>
          ) : null}
          {suggestError ? (
            <p role="alert" className="mt-3 text-sm text-red-700">
              {suggestError}
            </p>
          ) : null}
          {variants.length > 0 ? (
            <ul className="mt-4 grid gap-3 md:grid-cols-2">
              {variants.map((variant, index) => {
                const key = `${campaignId}-suggest-${index}`;
                const copyText = [
                  variant.headline,
                  variant.copy_text,
                  variant.description,
                ].join("\n");
                return (
                  <li
                    key={`${variant.headline}-${index}`}
                    className="rounded-md border border-zinc-200 p-3"
                  >
                    <p className="text-sm font-semibold">{variant.headline}</p>
                    <p className="mt-2 text-sm text-zinc-700">
                      {variant.copy_text}
                    </p>
                    <p className="mt-1 text-xs text-zinc-500">
                      {variant.description}
                    </p>
                    <p className="mt-2 text-xs text-zinc-500">
                      الزاوية: {variant.angle_ar}
                    </p>
                    <button
                      type="button"
                      onClick={() => void copy(key, copyText)}
                      className={`${secondaryButtonClass} mt-3`}
                    >
                      {copiedKey === key ? "تم النسخ" : "نسخ النص"}
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </section>

        <section className={cardClass}>
          <h2 className="text-base font-semibold">التحليلات السابقة</h2>
          {historyLoading ? (
            <p className="mt-3 text-sm text-zinc-500">جارٍ التحميل…</p>
          ) : null}
          {historyError ? (
            <p className="mt-3 text-sm text-red-700">
              تعذّر تحميل التحليلات السابقة.
            </p>
          ) : null}
          {!historyLoading && !historyError && history.length === 0 ? (
            <p className="mt-3 text-sm text-zinc-500">
              لا توجد تحليلات سابقة.
            </p>
          ) : null}
          {!historyLoading && !historyError && history.length > 0 ? (
            <ul className="mt-3 divide-y divide-zinc-200">
              {history.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => void openAnalysis(item.id)}
                    className={`flex w-full flex-wrap items-center justify-between gap-2 py-2 text-start text-sm hover:bg-zinc-50 ${
                      analysis?.id === item.id ? "font-semibold" : ""
                    }`}
                  >
                    <span>{formatDate(item.created_at)}</span>
                    <span className="flex items-center gap-2">
                      <span className="text-xs text-zinc-500">
                        {STATUS_LABELS[item.status]}
                      </span>
                      <span>
                        {item.demand_level
                          ? DEMAND_LABELS[item.demand_level]
                          : "—"}
                      </span>
                      {loadingId === item.id ? (
                        <span className="text-xs text-zinc-500">
                          جارٍ التحميل…
                        </span>
                      ) : null}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      </div>
    </AppShell>
  );
}

function AnalysisView({
  analysis,
  copiedKey,
  onCopy,
}: {
  analysis: Analysis;
  copiedKey: string | null;
  onCopy: CopyHandler;
}) {
  if (analysis.status === "degraded") {
    const reason = failureMessage(analysis.result);
    return (
      <section className="rounded-lg border border-amber-300 bg-amber-50 p-5 text-sm text-amber-900">
        <h2 className="text-base font-semibold">
          مزوّد الذكاء الاصطناعي غير متاح
        </h2>
        <p className="mt-2">
          لم يتم إنتاج أي اقتراح لأن مزوّد الذكاء الاصطناعي غير متاح حالياً.
        </p>
        {reason ? <p className="mt-1 text-xs">{reason}</p> : null}
      </section>
    );
  }

  if (analysis.status === "failed") {
    const reason = failureMessage(analysis.result);
    return (
      <section className="rounded-lg border border-red-300 bg-red-50 p-5 text-sm text-red-900">
        <h2 className="text-base font-semibold">فشل التحليل</h2>
        <p className="mt-2">تعذّر إكمال التحليل. حاول مرة أخرى.</p>
        {reason ? <p className="mt-1 text-xs">{reason}</p> : null}
      </section>
    );
  }

  if (!isAnalysisResult(analysis.result)) {
    return (
      <p className="text-sm text-red-700">
        تعذّر عرض نتيجة التحليل.
      </p>
    );
  }

  const result = analysis.result;
  const groups = ISSUE_TYPE_ORDER.map((type) => ({
    type,
    items: result.issues.filter((issue) => issue.type === type),
  })).filter((group) => group.items.length > 0);

  return (
    <section className={`${cardClass} space-y-6`}>
      <div>
        <h2 className="text-base font-semibold">نتيجة التحليل</h2>
        <p className="mt-1 text-xs text-zinc-500">
          {formatDate(analysis.created_at)} · {analysis.provider}
        </p>
      </div>

      <div>
        <div className="flex flex-wrap items-center gap-3">
          <span
            className={`rounded-full px-3 py-1 text-sm font-semibold ${DEMAND_STYLES[result.demand.level]}`}
          >
            {DEMAND_LABELS[result.demand.level]}
          </span>
          <span className="text-sm text-zinc-600">
            الثقة: {confidencePercent(result.demand.confidence)}
          </span>
        </div>
        <p className="mt-3 text-sm text-zinc-700">
          {result.demand.rationale_ar}
        </p>
      </div>

      <div>
        <h3 className="text-sm font-semibold">المشكلات المرصودة</h3>
        {groups.length === 0 ? (
          <p className="mt-2 text-sm text-zinc-500">
            لا توجد مشكلات مرصودة.
          </p>
        ) : (
          <div className="mt-2 space-y-4">
            {groups.map((group) => (
              <div key={group.type}>
                <h4 className="text-xs font-semibold text-zinc-500">
                  {ISSUE_TYPE_LABELS[group.type]}
                </h4>
                <ul className="mt-2 space-y-2">
                  {group.items.map((issue, index) => (
                    <li
                      key={`${issue.metric}-${index}`}
                      className="rounded-md border border-zinc-200 p-3"
                    >
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span
                          className={`rounded px-2 py-0.5 font-medium ${SEVERITY_STYLES[issue.severity]}`}
                        >
                          {SEVERITY_LABELS[issue.severity]}
                        </span>
                        <span className="font-mono text-zinc-600" dir="ltr">
                          {issue.metric}
                        </span>
                        <span className="text-zinc-600">
                          القيمة: {issue.observed}
                        </span>
                        <span className="text-zinc-600">
                          المرجع: {String(issue.benchmark)}
                        </span>
                      </div>
                      <p className="mt-2 text-sm text-zinc-700">
                        {issue.rationale_ar}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h3 className="text-sm font-semibold">التوصيات</h3>
        {result.recommendations.length === 0 ? (
          <p className="mt-2 text-sm text-zinc-500">لا توجد توصيات.</p>
        ) : (
          <ul className="mt-2 grid gap-3 md:grid-cols-2">
            {result.recommendations.map((recommendation, index) => {
              const changeKey = `${analysis.id}-change-${index}`;
              const copyKey = `${analysis.id}-copy-${index}`;
              return (
                <li
                  key={`${recommendation.action}-${index}`}
                  className="rounded-md border border-zinc-200 p-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold">
                      {ACTION_LABELS[recommendation.action]} ·{" "}
                      {recommendation.target}
                    </p>
                    <span className="text-xs text-zinc-500">
                      الثقة: {confidencePercent(recommendation.confidence)}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-zinc-700">
                    {recommendation.change_ar}
                  </p>
                  <p className="mt-1 text-xs text-zinc-500">
                    {recommendation.expected_impact_ar}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() =>
                        onCopy(changeKey, recommendation.change_ar)
                      }
                      className={secondaryButtonClass}
                    >
                      {copiedKey === changeKey ? "تم النسخ" : "نسخ التغيير"}
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        onCopy(copyKey, recommendation.copy_paste_ar)
                      }
                      className={secondaryButtonClass}
                    >
                      {copiedKey === copyKey
                        ? "تم النسخ"
                        : "نسخ النص الجاهز"}
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div>
        <h3 className="text-sm font-semibold">الخطوات التالية</h3>
        {result.next_steps_ar.length === 0 ? (
          <p className="mt-2 text-sm text-zinc-500">
            لا توجد خطوات إضافية.
          </p>
        ) : (
          <ul className="mt-2 space-y-2">
            {result.next_steps_ar.map((step, index) => (
              <li key={index}>
                <label className="flex items-start gap-2 text-sm text-zinc-700">
                  <input type="checkbox" className="mt-1" />
                  <span>{step}</span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
