"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";

import { AppShell } from "@/components/app-shell";
import { ApiError, apiFetch } from "@/lib/api";
import {
  formatDate,
  formatMoney,
  statusLabel,
  variationLabel,
  type AdVariation,
  type CampaignDetail,
  type MetricSnapshot,
} from "@/lib/campaigns";

type VariationWithAdSet = AdVariation & { adsetId: string };

type RowValues = {
  impressions: string;
  clicks: string;
  spend: string;
  reach: string;
  conversions: string;
};

const EMPTY_ROW: RowValues = {
  impressions: "",
  clicks: "",
  spend: "",
  reach: "",
  conversions: "",
};

const fieldClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900";
const labelClass = "block text-sm font-medium text-zinc-700";
const numberCellClass =
  "w-24 rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm outline-none focus:border-zinc-900";

function rowFor(rows: Record<string, RowValues>, id: string): RowValues {
  return rows[id] ?? EMPTY_ROW;
}

export default function CampaignSignalsPage() {
  const params = useParams<{ id: string }>();
  const campaignId = params.id;

  const [detail, setDetail] = useState<CampaignDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<"not_found" | "error" | null>(
    null,
  );

  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [rows, setRows] = useState<Record<string, RowValues>>({});
  const [signals, setSignals] = useState<MetricSnapshot[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [notAvailable, setNotAvailable] = useState(false);

  const loadDetail = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await apiFetch<CampaignDetail>(`/campaigns/${campaignId}`);
      setDetail(data);
      const loaded = (data.ad_sets ?? []).flatMap((adSet) =>
        (adSet.variations ?? []).map((variation) => ({ ...variation, adsetId: adSet.id })),
      );
      setRows(
        Object.fromEntries(loaded.map((variation) => [variation.id, { ...EMPTY_ROW }])),
      );
    } catch (error) {
      setDetail(null);
      setLoadError(
        error instanceof ApiError && error.status === 404 ? "not_found" : "error",
      );
    } finally {
      setLoading(false);
    }
  }, [campaignId]);

  useEffect(() => {
    let active = true;
    apiFetch<CampaignDetail>(`/campaigns/${campaignId}`)
      .then((data) => {
        if (!active) return;
        setDetail(data);
        setSignals(data.signals ?? []);
        const loaded = (data.ad_sets ?? []).flatMap((adSet) =>
          (adSet.variations ?? []).map((variation) => ({
            ...variation,
            adsetId: adSet.id,
          })),
        );
        setRows(
          Object.fromEntries(
            loaded.map((variation) => [variation.id, { ...EMPTY_ROW }]),
          ),
        );
      })
      .catch((error) => {
        if (!active) return;
        setDetail(null);
        setLoadError(
          error instanceof ApiError && error.status === 404
            ? "not_found"
            : "error",
        );
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    apiFetch<MetricSnapshot[]>(`/campaigns/${campaignId}/signals`)
      .then((data) => {
        if (!active) return;
        setSignals(Array.isArray(data) ? data : []);
        setNotAvailable(false);
      })
      .catch((error) => {
        if (
          active &&
          error instanceof ApiError &&
          error.status === 404
        ) {
          setNotAvailable(true);
        }
      });

    return () => {
      active = false;
    };
  }, [campaignId]);

  const variations = useMemo<VariationWithAdSet[]>(
    () =>
      (detail?.ad_sets ?? []).flatMap((adSet) =>
        (adSet.variations ?? []).map((variation) => ({
          ...variation,
          adsetId: adSet.id,
        })),
      ),
    [detail],
  );

  const snapshots = signals;

  function updateRow(id: string, field: keyof RowValues, value: string) {
    setRows((current) => ({
      ...current,
      [id]: { ...rowFor(current, id), [field]: value },
    }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError(null);
    setSubmitted(false);
    setNotAvailable(false);

    if (periodEnd <= periodStart) {
      setSubmitError("تاريخ النهاية يجب أن يكون بعد تاريخ البداية.");
      return;
    }

    if (variations.length === 0) {
      setSubmitError("أضف مجموعات إعلانية ونصوصاً إلى الحملة أولاً.");
      return;
    }

    const signalRows = variations.map((variation) => {
      const row = rowFor(rows, variation.id);
      return {
        adset_id: variation.adsetId,
        ad_variation_id: variation.id,
        impressions: Number(row.impressions || 0),
        clicks: Number(row.clicks || 0),
        spend_minor: Math.round(Number(row.spend || 0) * 100),
        reach: Number(row.reach || 0),
        conversions: Number(row.conversions || 0),
      };
    });

    setSubmitting(true);
    try {
      await apiFetch(`/campaigns/${campaignId}/signals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: detail?.provider,
          period_start: `${periodStart}T00:00:00.000Z`,
          period_end: `${periodEnd}T23:59:59.000Z`,
          rows: signalRows,
        }),
      });
      setSubmitted(true);
      setNotAvailable(false);
      try {
        const updated = await apiFetch<MetricSnapshot[]>(
          `/campaigns/${campaignId}/signals`,
        );
        setSignals(Array.isArray(updated) ? updated : []);
      } catch {
        // The window was accepted; the refreshed list is best-effort.
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setNotAvailable(true);
      } else {
        setSubmitError("تعذّر إرسال الإشارات. حاول مرة أخرى.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">إشارات الحملة</h1>
            <p className="mt-1 text-sm text-zinc-500">
              سجّل نافذة سبعة أيام من مؤشرات الأداء لكل إعلان.
            </p>
          </div>
          <Link
            href="/campaigns"
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
          >
            العودة إلى الحملات
          </Link>
        </div>

        {loading ? (
          <p className="text-sm text-zinc-500">جارٍ التحميل…</p>
        ) : null}

        {loadError === "not_found" ? (
          <p className="text-sm text-red-700">الحملة غير موجودة.</p>
        ) : null}

        {loadError === "error" ? (
          <div className="text-sm text-red-700">
            <p>تعذّر تحميل الحملة. تحقّق من اتصال الخادم.</p>
            <button
              type="button"
              onClick={() => void loadDetail()}
              className="mt-2 rounded-md border border-zinc-300 px-3 py-1.5 text-zinc-700"
            >
              إعادة المحاولة
            </button>
          </div>
        ) : null}

        {detail ? (
          <>
            <div className="rounded-lg border border-zinc-200 bg-white p-4">
              <p className="font-medium">{detail.name}</p>
              <p className="mt-1 text-xs text-zinc-500">
                {statusLabel(detail.status)} ·{" "}
                {formatMoney(detail.budget_minor, detail.currency)} ·{" "}
                {formatDate(detail.start_at)} — {formatDate(detail.end_at)}
              </p>
            </div>

            {notAvailable ? (
              <div
                role="status"
                className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900"
              >
                تسجيل الإشارات غير متاح بعد. سيُفعّل هذا المسار في تحديث لاحق.
              </div>
            ) : null}

            <section className="rounded-lg border border-zinc-200 bg-white p-5">
              <h2 className="text-base font-semibold">نافذة جديدة</h2>
              <form onSubmit={handleSubmit} className="mt-4 space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <label className={labelClass} htmlFor="period_start">
                      بداية الفترة
                    </label>
                    <input
                      id="period_start"
                      type="date"
                      required
                      value={periodStart}
                      onChange={(event) => setPeriodStart(event.target.value)}
                      className={fieldClass}
                    />
                  </div>
                  <div>
                    <label className={labelClass} htmlFor="period_end">
                      نهاية الفترة
                    </label>
                    <input
                      id="period_end"
                      type="date"
                      required
                      value={periodEnd}
                      onChange={(event) => setPeriodEnd(event.target.value)}
                      className={fieldClass}
                    />
                  </div>
                </div>

                {variations.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-zinc-200">
                          <th className="py-2 text-start font-medium">الإعلان</th>
                          <th className="py-2 text-start font-medium">
                            مرات الظهور
                          </th>
                          <th className="py-2 text-start font-medium">النقرات</th>
                          <th className="py-2 text-start font-medium">
                            الإنفاق (ر.س)
                          </th>
                          <th className="py-2 text-start font-medium">الوصول</th>
                          <th className="py-2 text-start font-medium">
                            التحويلات
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {variations.map((variation) => {
                          const row = rowFor(rows, variation.id);
                          const label = variationLabel(variation);
                          return (
                            <tr key={variation.id} className="border-b border-zinc-100">
                              <td className="py-2 pe-3">{label}</td>
                              <td className="py-2 pe-3">
                                <input
                                  type="number"
                                  min="0"
                                  aria-label={`${label} - مرات الظهور`}
                                  value={row.impressions}
                                  onChange={(event) =>
                                    updateRow(variation.id, "impressions", event.target.value)
                                  }
                                  className={numberCellClass}
                                />
                              </td>
                              <td className="py-2 pe-3">
                                <input
                                  type="number"
                                  min="0"
                                  aria-label={`${label} - النقرات`}
                                  value={row.clicks}
                                  onChange={(event) =>
                                    updateRow(variation.id, "clicks", event.target.value)
                                  }
                                  className={numberCellClass}
                                />
                              </td>
                              <td className="py-2 pe-3">
                                <input
                                  type="number"
                                  min="0"
                                  step="0.01"
                                  aria-label={`${label} - الإنفاق`}
                                  value={row.spend}
                                  onChange={(event) =>
                                    updateRow(variation.id, "spend", event.target.value)
                                  }
                                  className={numberCellClass}
                                />
                              </td>
                              <td className="py-2 pe-3">
                                <input
                                  type="number"
                                  min="0"
                                  aria-label={`${label} - الوصول`}
                                  value={row.reach}
                                  onChange={(event) =>
                                    updateRow(variation.id, "reach", event.target.value)
                                  }
                                  className={numberCellClass}
                                />
                              </td>
                              <td className="py-2">
                                <input
                                  type="number"
                                  min="0"
                                  aria-label={`${label} - التحويلات`}
                                  value={row.conversions}
                                  onChange={(event) =>
                                    updateRow(variation.id, "conversions", event.target.value)
                                  }
                                  className={numberCellClass}
                                />
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-sm text-zinc-500">
                    لا توجد نصوص إعلانية في هذه الحملة بعد.
                  </p>
                )}

                <button
                  type="submit"
                  disabled={submitting || variations.length === 0}
                  className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  {submitting ? "جارٍ الإرسال…" : "إرسال الإشارات"}
                </button>

                {submitError ? (
                  <p role="alert" className="text-sm text-red-700">
                    {submitError}
                  </p>
                ) : null}
                {submitted ? (
                  <p role="status" className="text-sm text-green-700">
                    تم تسجيل نافذة الإشارات.
                  </p>
                ) : null}
              </form>
            </section>

            <section className="rounded-lg border border-zinc-200 bg-white p-5">
              <h2 className="text-base font-semibold">النوافذ السابقة</h2>
              {snapshots.length === 0 ? (
                <p className="mt-3 text-sm text-zinc-500">
                  لم تُسجَّل أي نوافذ بعد.
                </p>
              ) : (
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-zinc-200">
                        <th className="py-2 text-start font-medium">الفترة</th>
                        <th className="py-2 text-start font-medium">مرات الظهور</th>
                        <th className="py-2 text-start font-medium">النقرات</th>
                        <th className="py-2 text-start font-medium">الإنفاق</th>
                        <th className="py-2 text-start font-medium">نسبة النقر</th>
                        <th className="py-2 text-start font-medium">تكلفة النقرة</th>
                        <th className="py-2 text-start font-medium">التحويلات</th>
                      </tr>
                    </thead>
                    <tbody>
                      {snapshots.map((snapshot, index) => (
                        <tr
                          key={`${snapshot.period_start}-${snapshot.period_end}-${index}`}
                          className="border-b border-zinc-100"
                        >
                          <td className="py-2 pe-3">
                            {formatDate(snapshot.period_start)} —{" "}
                            {formatDate(snapshot.period_end)}
                          </td>
                          <td className="py-2 pe-3">{snapshot.impressions}</td>
                          <td className="py-2 pe-3">{snapshot.clicks}</td>
                          <td className="py-2 pe-3">
                            {formatMoney(snapshot.spend_minor, detail.currency)}
                          </td>
                          <td className="py-2 pe-3">
                            {snapshot.ctr !== null && snapshot.ctr !== undefined
                              ? `${(snapshot.ctr * 100).toFixed(2)}%`
                              : "—"}
                          </td>
                          <td className="py-2 pe-3">
                            {snapshot.cpc_minor !== null &&
                            snapshot.cpc_minor !== undefined
                              ? formatMoney(snapshot.cpc_minor, detail.currency)
                              : "—"}
                          </td>
                          <td className="py-2">{snapshot.conversions ?? 0}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        ) : null}
      </div>
    </AppShell>
  );
}
