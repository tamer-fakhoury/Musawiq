"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { AppShell } from "@/components/app-shell";
import { ApiError, apiFetch } from "@/lib/api";
import {
  formatDate,
  sentimentLabel,
  sourceLabel,
  type FeedbackItem,
} from "@/lib/feedback";

const fieldClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900";
const labelClass = "block text-sm font-medium text-zinc-700";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export default function FeedbackPage() {
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [text, setText] = useState("");
  const [language, setLanguage] = useState("");
  const [sentiment, setSentiment] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadFeedback = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch<FeedbackItem[]>("/feedback?limit=100");
      setItems(Array.isArray(data) ? data : []);
    } catch (loadError) {
      setError(errorMessage(loadError, "تعذر تحميل الملاحظات."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    apiFetch<FeedbackItem[]>("/feedback?limit=100")
      .then((data) => {
        if (active) {
          setItems(Array.isArray(data) ? data : []);
          setLoading(false);
        }
      })
      .catch((loadError) => {
        if (active) {
          setError(errorMessage(loadError, "تعذر تحميل الملاحظات."));
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  async function submitManual(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    if (!text.trim()) {
      setError("اكتب نص الملاحظة أولاً.");
      return;
    }
    setBusy(true);
    try {
      await apiFetch<FeedbackItem>("/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          language: language || null,
          sentiment: sentiment || null,
        }),
      });
      setText("");
      setLanguage("");
      setSentiment("");
      setNotice("تم حفظ الملاحظة.");
      await loadFeedback();
    } catch (submitError) {
      setError(errorMessage(submitError, "تعذر حفظ الملاحظة."));
    } finally {
      setBusy(false);
    }
  }

  async function submitFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    if (!file) {
      setError("اختر ملفاً أولاً.");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    setBusy(true);
    try {
      const result = await apiFetch<{ count: number }>("/feedback/file", {
        method: "POST",
        body: form,
      });
      setFile(null);
      setNotice(`تم استيراد ${result.count} ملاحظة.`);
      await loadFeedback();
    } catch (submitError) {
      setError(errorMessage(submitError, "تعذر استيراد الملف."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold">ملاحظات العملاء</h1>
          <p className="mt-1 text-sm text-zinc-500">
            سجّل ملاحظة يدوياً أو استورد ملفاً بصيغة CSV أو TXT أو XLSX.
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

        <div className="grid gap-6 xl:grid-cols-2">
          <section className="rounded-lg border border-zinc-200 bg-white p-5">
            <h2 className="text-base font-semibold">إدخال يدوي</h2>
            <form onSubmit={submitManual} className="mt-4 space-y-4">
              <div>
                <label className={labelClass} htmlFor="feedback-text">
                  النص
                </label>
                <textarea
                  id="feedback-text"
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  rows={4}
                  className={fieldClass}
                />
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className={labelClass} htmlFor="feedback-language">
                    اللغة
                  </label>
                  <input
                    id="feedback-language"
                    value={language}
                    onChange={(event) => setLanguage(event.target.value)}
                    placeholder="ar / en"
                    className={fieldClass}
                  />
                </div>
                <div>
                  <label className={labelClass} htmlFor="feedback-sentiment">
                    المشاعر
                  </label>
                  <select
                    id="feedback-sentiment"
                    value={sentiment}
                    onChange={(event) => setSentiment(event.target.value)}
                    className={fieldClass}
                  >
                    <option value="">غير محدد</option>
                    <option value="positive">إيجابي</option>
                    <option value="neutral">محايد</option>
                    <option value="negative">سلبي</option>
                  </select>
                </div>
              </div>
              <button
                type="submit"
                disabled={busy}
                className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {busy ? "جارٍ الحفظ…" : "حفظ الملاحظة"}
              </button>
            </form>
          </section>

          <section className="rounded-lg border border-zinc-200 bg-white p-5">
            <h2 className="text-base font-semibold">استيراد ملف</h2>
            <form onSubmit={submitFile} className="mt-4 space-y-4">
              <div>
                <label className={labelClass} htmlFor="feedback-file">
                  الملف
                </label>
                <input
                  id="feedback-file"
                  type="file"
                  accept=".csv,.txt,.xlsx"
                  onChange={(event) =>
                    setFile(event.target.files?.[0] ?? null)
                  }
                  className={fieldClass}
                />
              </div>
              <p className="text-xs text-zinc-500">
                UTF-8 فقط. يمكن أن يحتوي CSV/XLSX على أعمدة text وlanguage
                وsentiment.
              </p>
              <button
                type="submit"
                disabled={busy}
                className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {busy ? "جارٍ الاستيراد…" : "استيراد الملف"}
              </button>
            </form>
          </section>
        </div>

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">الملاحظات المسجلة</h2>
            <button
              type="button"
              onClick={() => void loadFeedback()}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
            >
              تحديث
            </button>
          </div>
          {loading ? (
            <p className="mt-4 text-sm text-zinc-500">جارٍ التحميل…</p>
          ) : null}
          {!loading && items.length === 0 ? (
            <p className="mt-4 text-sm text-zinc-500">لا توجد ملاحظات بعد.</p>
          ) : null}
          {!loading && items.length > 0 ? (
            <ul className="mt-4 divide-y divide-zinc-200">
              {items.map((item) => (
                <li key={item.id} className="py-3">
                  <p className="text-sm text-zinc-800">{item.text}</p>
                  <p className="mt-1 text-xs text-zinc-500">
                    {sourceLabel(item.source)}
                    {" • "}
                    {sentimentLabel(item.sentiment)}
                    {" • "}
                    {item.language ?? "بدون لغة"}
                    {" • "}
                    {formatDate(item.captured_at)}
                  </p>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      </div>
    </AppShell>
  );
}
