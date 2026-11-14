"use client";

import { useEffect, useState, type FormEvent } from "react";

import { AppShell } from "@/components/app-shell";
import { ApiError, apiFetch } from "@/lib/api";

const fieldClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900";
const labelClass = "block text-sm font-medium text-zinc-700";

type Batch = {
  id: string;
  status: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  created_at: string;
};

type MappingSuggestion = {
  headers: string[];
  suggested: Record<string, string>;
  missing_required: string[];
};

type Preview = {
  counts: Record<string, number>;
  rows: { row_number: number; status: string }[];
  issues: {
    total: number;
    items: {
      row_number: number;
      field_name: string | null;
      issue_code: string;
      message: string;
    }[];
  };
};

function errorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

export default function ImportsPage() {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [selected, setSelected] = useState<Batch | null>(null);
  const [mappingText, setMappingText] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadBatches() {
    const data = await apiFetch<Batch[]>("/imports");
    setBatches(Array.isArray(data) ? data : []);
    return data;
  }

  useEffect(() => {
    let active = true;
    apiFetch<Batch[]>("/imports")
      .then((data) => {
        if (active) setBatches(Array.isArray(data) ? data : []);
      })
      .catch((loadError) => {
        if (active) setError(errorMessage(loadError, "تعذر تحميل الاستيرادات."));
      });
    return () => {
      active = false;
    };
  }, []);

  async function openBatch(batch: Batch) {
    setSelected(batch);
    setPreview(null);
    setError(null);
    setNotice(null);
    try {
      const suggestion = await apiFetch<MappingSuggestion>(
        `/imports/${batch.id}/mapping`,
      );
      setMappingText(JSON.stringify(suggestion.suggested, null, 2));
    } catch (mappingError) {
      setMappingText("");
      setError(errorMessage(mappingError, "تعذر اقتراح الأعمدة."));
    }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("اختر ملف CSV أولاً.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    const form = new FormData();
    form.append("file", file);
    try {
      await apiFetch("/imports", { method: "POST", body: form });
      setFile(null);
      setNotice("تم رفع الملف.");
      await loadBatches();
    } catch (uploadError) {
      setError(errorMessage(uploadError, "تعذر رفع الملف."));
    } finally {
      setBusy(false);
    }
  }

  async function saveMapping() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const mapping = JSON.parse(mappingText) as Record<string, string>;
      await apiFetch(`/imports/${selected.id}/mapping`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mapping }),
      });
      setNotice("تم حفظ ربط الأعمدة.");
    } catch (mappingError) {
      setError(errorMessage(mappingError, "تعذر حفظ ربط الأعمدة."));
    } finally {
      setBusy(false);
    }
  }

  async function validate() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/imports/${selected.id}/validate`, { method: "POST" });
      setNotice("تم التحقق من الملف.");
      const data = await loadBatches();
      const refreshed = data.find((item) => item.id === selected.id) ?? selected;
      setSelected(refreshed);
    } catch (validationError) {
      setError(errorMessage(validationError, "تعذر التحقق من الملف."));
    } finally {
      setBusy(false);
    }
  }

  async function loadPreview() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      setPreview(
        await apiFetch<Preview>(`/imports/${selected.id}/preview`),
      );
    } catch (previewError) {
      setError(errorMessage(previewError, "تعذر تحميل المعاينة."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold">الاستيراد</h1>
          <p className="mt-1 text-sm text-zinc-500">
            ارفع CSV، اربط الأعمدة، تحقق، ثم راجع المعاينة. الحفظ النهائي غير
            مفعّل بعد؛ هذه المرحلة للمعاينة فقط.
          </p>
        </div>
        {error ? <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
        {notice ? <p role="status" className="rounded-md bg-green-50 p-3 text-sm text-green-700">{notice}</p> : null}

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-base font-semibold">رفع ملف</h2>
          <form onSubmit={upload} className="mt-4 flex flex-wrap items-end gap-3">
            <div className="min-w-64 flex-1">
              <label className={labelClass} htmlFor="import-file">ملف CSV</label>
              <input id="import-file" type="file" accept=".csv,text/csv" onChange={(event) => setFile(event.target.files?.[0] ?? null)} className={fieldClass} />
            </div>
            <button type="submit" disabled={busy} className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">رفع</button>
          </form>
        </section>

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-base font-semibold">الملفات</h2>
          <ul className="mt-3 divide-y divide-zinc-200">
            {batches.map((batch) => (
              <li key={batch.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div>
                  <p className="text-sm font-medium">{batch.status}</p>
                  <p className="text-xs text-zinc-500">{batch.id.slice(0, 8)} • صالح {batch.valid_rows} • غير صالح {batch.invalid_rows}</p>
                </div>
                <button type="button" onClick={() => void openBatch(batch)} className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm">فتح</button>
              </li>
            ))}
          </ul>
        </section>

        {selected ? (
          <section className="rounded-lg border border-zinc-200 bg-white p-5">
            <h2 className="text-base font-semibold">ربط الأعمدة والتحقق</h2>
            <p className="mt-1 text-xs text-zinc-500">الملف: {selected.id}</p>
            <label className={`${labelClass} mt-4`} htmlFor="mapping-json">تعيين الأعمدة (JSON)</label>
            <textarea id="mapping-json" value={mappingText} onChange={(event) => setMappingText(event.target.value)} rows={8} dir="ltr" className={fieldClass} />
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" disabled={busy} onClick={() => void saveMapping()} className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm">حفظ الربط</button>
              <button type="button" disabled={busy} onClick={() => void validate()} className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white">تحقق</button>
              <button type="button" disabled={busy} onClick={() => void loadPreview()} className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm">معاينة</button>
            </div>
            {preview ? (
              <div className="mt-4 text-sm">
                <p className="font-medium">الملخص</p>
                <pre className="mt-1 overflow-auto rounded bg-zinc-50 p-2 text-xs" dir="ltr">{JSON.stringify(preview.counts, null, 2)}</pre>
                <p className="mt-3 font-medium">المشكلات: {preview.issues.total}</p>
                <ul className="mt-1 space-y-1 text-xs text-red-700">
                  {preview.issues.items.slice(0, 10).map((issue, index) => (
                    <li key={`${issue.row_number}-${index}`}>صف {issue.row_number}: {issue.issue_code} — {issue.message}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>
        ) : null}
      </div>
    </AppShell>
  );
}
