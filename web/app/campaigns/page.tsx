"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { AppShell } from "@/components/app-shell";
import { apiFetch } from "@/lib/api";
import {
  PROVIDERS,
  formatDate,
  formatMoney,
  providerLabel,
  statusLabel,
  variationLabel,
  type Campaign,
  type CampaignDetail,
} from "@/lib/campaigns";

const fieldClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900";
const labelClass = "block text-sm font-medium text-zinc-700";

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState(false);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CampaignDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(false);

  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [createdMessage, setCreatedMessage] = useState<string | null>(null);

  const loadCampaigns = useCallback(async () => {
    setLoading(true);
    setListError(false);
    try {
      const data = await apiFetch<Campaign[]>("/campaigns");
      setCampaigns(Array.isArray(data) ? data : []);
    } catch {
      setListError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    apiFetch<Campaign[]>("/campaigns")
      .then((data) => {
        if (active) {
          setCampaigns(Array.isArray(data) ? data : []);
        }
      })
      .catch(() => {
        if (active) {
          setListError(true);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  async function openCampaign(id: string) {
    setSelectedId(id);
    setDetail(null);
    setDetailError(false);
    setDetailLoading(true);
    try {
      setDetail(await apiFetch<CampaignDetail>(`/campaigns/${id}`));
    } catch {
      setDetailError(true);
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const startAt = String(values.get("start_at") ?? "");
    const endAt = String(values.get("end_at") ?? "");

    setFormError(null);
    setCreatedMessage(null);

    if (endAt <= startAt) {
      setFormError("تاريخ النهاية يجب أن يكون بعد تاريخ البداية.");
      return;
    }

    setCreating(true);
    try {
      const created = await apiFetch<{ id?: string }>("/campaigns", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          test_id: String(values.get("test_id") ?? ""),
          name: String(values.get("name") ?? ""),
          provider: String(values.get("provider") ?? "meta"),
          objective: String(values.get("objective") ?? ""),
          budget_type: String(values.get("budget_type") ?? "total"),
          budget_minor: Math.round(Number(values.get("budget") ?? 0) * 100),
          currency: "SAR",
          start_at: `${startAt}T00:00:00.000Z`,
          end_at: `${endAt}T00:00:00.000Z`,
        }),
      });

      form.reset();
      setCreatedMessage("تم إنشاء الحملة.");
      await loadCampaigns();
      if (created.id) {
        await openCampaign(created.id);
      }
    } catch {
      setFormError("تعذّر إنشاء الحملة. تحقّق من البيانات وحاول مرة أخرى.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold">الحملات</h1>
          <p className="mt-1 text-sm text-zinc-500">
            أنشئ حملة إعلانية وحدّد الميزانية والفترة الزمنية.
          </p>
        </div>

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-base font-semibold">حملة جديدة</h2>
          <form onSubmit={handleCreate} className="mt-4 grid gap-4 md:grid-cols-2">
            <div>
              <label className={labelClass} htmlFor="test_id">
                معرّف الاختبار
              </label>
              <input
                id="test_id"
                name="test_id"
                required
                placeholder="UUID"
                dir="ltr"
                className={fieldClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="name">
                اسم الحملة
              </label>
              <input id="name" name="name" required className={fieldClass} />
            </div>
            <div>
              <label className={labelClass} htmlFor="provider">
                المنصّة
              </label>
              <select
                id="provider"
                name="provider"
                className={fieldClass}
                defaultValue="meta"
              >
                {PROVIDERS.map((provider) => (
                  <option key={provider.value} value={provider.value}>
                    {provider.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelClass} htmlFor="objective">
                الهدف
              </label>
              <input
                id="objective"
                name="objective"
                required
                className={fieldClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="budget_type">
                نوع الميزانية
              </label>
              <select
                id="budget_type"
                name="budget_type"
                className={fieldClass}
                defaultValue="total"
              >
                <option value="total">إجمالية</option>
                <option value="daily">يومية</option>
              </select>
            </div>
            <div>
              <label className={labelClass} htmlFor="budget">
                الميزانية (ر.س)
              </label>
              <input
                id="budget"
                name="budget"
                type="number"
                min="0.01"
                step="0.01"
                required
                className={fieldClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="currency">
                العملة
              </label>
              <input
                id="currency"
                name="currency"
                value="SAR"
                readOnly
                className={`${fieldClass} bg-zinc-50`}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="start_at">
                تاريخ البداية
              </label>
              <input
                id="start_at"
                name="start_at"
                type="date"
                required
                className={fieldClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="end_at">
                تاريخ النهاية
              </label>
              <input
                id="end_at"
                name="end_at"
                type="date"
                required
                className={fieldClass}
              />
            </div>
            <div className="flex items-end">
              <button
                type="submit"
                disabled={creating}
                className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {creating ? "جارٍ الإنشاء…" : "إنشاء الحملة"}
              </button>
            </div>
          </form>
          {formError ? (
            <p role="alert" className="mt-3 text-sm text-red-700">
              {formError}
            </p>
          ) : null}
          {createdMessage ? (
            <p role="status" className="mt-3 text-sm text-green-700">
              {createdMessage}
            </p>
          ) : null}
        </section>

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-base font-semibold">قائمة الحملات</h2>
          {loading ? (
            <p className="mt-3 text-sm text-zinc-500">جارٍ التحميل…</p>
          ) : null}
          {listError ? (
            <div className="mt-3 text-sm text-red-700">
              <p>تعذّر تحميل الحملات. تحقّق من اتصال الخادم.</p>
              <button
                type="button"
                onClick={() => void loadCampaigns()}
                className="mt-2 rounded-md border border-zinc-300 px-3 py-1.5 text-zinc-700"
              >
                إعادة المحاولة
              </button>
            </div>
          ) : null}
          {!loading && !listError && campaigns.length === 0 ? (
            <p className="mt-3 text-sm text-zinc-500">لا توجد حملات بعد.</p>
          ) : null}
          {!loading && !listError && campaigns.length > 0 ? (
            <ul className="mt-3 divide-y divide-zinc-200">
              {campaigns.map((campaign) => (
                <li
                  key={campaign.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-3"
                >
                  <div>
                    <p className="font-medium">{campaign.name}</p>
                    <p className="mt-0.5 text-xs text-zinc-500">
                      {providerLabel(campaign.provider)} ·{" "}
                      {statusLabel(campaign.status)} ·{" "}
                      {formatMoney(campaign.budget_minor, campaign.currency)}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => void openCampaign(campaign.id)}
                      className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
                    >
                      التفاصيل
                    </button>
                    <Link
                      href={`/campaigns/${campaign.id}/signals`}
                      className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white"
                    >
                      الإشارات
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
        </section>

        {selectedId ? (
          <section className="rounded-lg border border-zinc-200 bg-white p-5">
            <h2 className="text-base font-semibold">تفاصيل الحملة</h2>
            {detailLoading ? (
              <p className="mt-3 text-sm text-zinc-500">جارٍ التحميل…</p>
            ) : null}
            {detailError ? (
              <p className="mt-3 text-sm text-red-700">
                تعذّر تحميل تفاصيل الحملة.
              </p>
            ) : null}
            {detail ? (
              <div className="mt-3 space-y-4">
                <div>
                  <h3 className="text-lg font-semibold">{detail.name}</h3>
                  <p className="mt-1 text-sm text-zinc-500">
                    {providerLabel(detail.provider)} ·{" "}
                    {statusLabel(detail.status)} ·{" "}
                    {formatMoney(detail.budget_minor, detail.currency)} ·{" "}
                    {formatDate(detail.start_at)} — {formatDate(detail.end_at)}
                  </p>
                  <p className="mt-1 text-sm text-zinc-600">
                    الهدف: {detail.objective}
                  </p>
                </div>

                <div>
                  <h3 className="text-sm font-semibold">مجموعات الإعلانات</h3>
                  {detail.ad_sets && detail.ad_sets.length > 0 ? (
                    <ul className="mt-2 space-y-3">
                      {detail.ad_sets.map((adSet) => (
                        <li
                          key={adSet.id}
                          className="rounded-md border border-zinc-200 p-3"
                        >
                          <p className="text-sm font-medium">
                            {adSet.name} · {statusLabel(adSet.status)}
                          </p>
                          {adSet.variations && adSet.variations.length > 0 ? (
                            <ul className="mt-2 space-y-2">
                              {adSet.variations.map((variation) => (
                                <li
                                  key={variation.id}
                                  className="rounded bg-zinc-50 p-2 text-sm"
                                >
                                  <p className="font-medium">
                                    {variationLabel(variation)} ·{" "}
                                    {statusLabel(variation.status)}
                                  </p>
                                  <p className="mt-1 text-zinc-600">
                                    {variation.copy_text}
                                  </p>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="mt-2 text-sm text-zinc-500">
                              لا توجد نصوص إعلانية بعد.
                            </p>
                          )}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-2 text-sm text-zinc-500">
                      لا توجد مجموعات إعلانية بعد.
                    </p>
                  )}
                </div>
              </div>
            ) : null}
          </section>
        ) : null}
      </div>
    </AppShell>
  );
}
