"use client";

import { useState, type FormEvent } from "react";

import { AppShell } from "@/components/app-shell";
import { ApiError } from "@/lib/api";
import {
  configureChannel,
  createDraft,
  generateCopy,
  generatePage,
  getPage,
  uploadImage,
  verifyChannel,
  type LandingPage,
} from "@/lib/landing-pages";

const field =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900";
const label = "block text-sm font-medium text-zinc-700";
const button =
  "rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-40";

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : "حدث خطأ غير متوقع";
}

export default function LandingPagesPage() {
  const [conceptId, setConceptId] = useState("");
  const [name, setName] = useState("آلة قهوة منزلية");
  const [description, setDescription] = useState("قهوة طازجة بخطوات بسيطة");
  const [price, setPrice] = useState("4999");
  const [currency, setCurrency] = useState("USD");
  const [language, setLanguage] = useState("ar");
  const [market, setMarket] = useState("SA");
  const [method, setMethod] = useState<"whatsapp" | "cod">("whatsapp");
  const [whatsapp, setWhatsapp] = useState("+966500000000");
  const [page, setPage] = useState<LandingPage | null>(null);
  const [copy, setCopy] = useState<Record<string, string> | null>(null);
  const [verification, setVerification] = useState<{
    valid: boolean;
    errors: string[];
  } | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  async function refresh(id: string) {
    setPage(await getPage(id));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      const created = await createDraft(conceptId.trim(), {
        name,
        description,
        price_minor: Number(price),
        currency,
        language,
        target_market: market,
        image_file_ids: [],
        order_method: { type: method, whatsapp_number: whatsapp },
      });
      setPage(created);
      setCopy(null);
      setVerification(null);
      setJobId(null);
    });
  }

  return (
    <AppShell>
      <h1 className="text-xl font-semibold">صفحات الهبوط</h1>
      <p className="mt-1 text-sm text-zinc-500">
        إنشاء مسودة، توليد النصوص، وتهيئة وسيلة الطلب (واتساب أو الدفع عند
        الاستلام).
      </p>

      {error ? (
        <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      <form onSubmit={submit} className="mt-6 grid max-w-3xl gap-4 md:grid-cols-2">
        <label className={label}>
          معرف مفهوم المنتج
          <input
            className={field}
            value={conceptId}
            onChange={(event) => setConceptId(event.target.value)}
            placeholder="UUID"
            required
          />
        </label>
        <label className={label}>
          اسم المنتج
          <input
            className={field}
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
          />
        </label>
        <label className={label}>
          الوصف
          <input
            className={field}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        <label className={label}>
          السعر (أصغر وحدة)
          <input
            className={field}
            value={price}
            onChange={(event) => setPrice(event.target.value)}
            inputMode="numeric"
            required
          />
        </label>
        <label className={label}>
          العملة
          <input
            className={field}
            value={currency}
            onChange={(event) => setCurrency(event.target.value)}
          />
        </label>
        <label className={label}>
          اللغة
          <input
            className={field}
            value={language}
            onChange={(event) => setLanguage(event.target.value)}
          />
        </label>
        <label className={label}>
          السوق
          <input
            className={field}
            value={market}
            onChange={(event) => setMarket(event.target.value)}
          />
        </label>
        <label className={label}>
          وسيلة الطلب
          <select
            className={field}
            value={method}
            onChange={(event) =>
              setMethod(event.target.value as "whatsapp" | "cod")
            }
          >
            <option value="whatsapp">واتساب</option>
            <option value="cod">الدفع عند الاستلام</option>
          </select>
        </label>
        {method === "whatsapp" ? (
          <label className={label}>
            رقم واتساب
            <input
              className={field}
              value={whatsapp}
              onChange={(event) => setWhatsapp(event.target.value)}
            />
          </label>
        ) : null}
        <div className="md:col-span-2">
          <button className={button} disabled={busy} type="submit">
            إنشاء مسودة
          </button>
        </div>
      </form>

      {page ? (
        <section className="mt-8 space-y-4 border-t border-zinc-200 pt-6">
          <p className="text-sm text-zinc-600">
            المسودة: <code>{page.id}</code> — الإصدار {page.draft_version} —
            الاتجاه {page.direction}
          </p>

          <div className="flex flex-wrap gap-2">
            <label className={`${button} cursor-pointer`}>
              رفع صورة
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (!file) return;
                  run(async () => {
                    const image = await uploadImage(file);
                    setPage({
                      ...page,
                      image_file_ids: [...page.image_file_ids, image.id],
                    });
                  });
                }}
              />
            </label>
            <button
              className={button}
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const generated = await generateCopy(page.id);
                  setCopy(generated as unknown as Record<string, string>);
                  await refresh(page.id);
                })
              }
            >
              توليد النصوص
            </button>
            <button
              className={button}
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const result = await generatePage(page.id);
                  setJobId(result.job_id);
                  await refresh(page.id);
                })
              }
            >
              توليد الصفحة
            </button>
            <button
              className={button}
              disabled={busy}
              onClick={() =>
                run(async () => {
                  await configureChannel(
                    page.id,
                    method === "whatsapp"
                      ? {
                          type: "whatsapp",
                          whatsapp_number: whatsapp,
                          whatsapp_message_template: "أرغب بطلب هذا المنتج",
                        }
                      : {
                          type: "cod",
                          cod_form_schema: {
                            fields: [
                              { name: "phone", required: true },
                              { name: "address", required: true },
                            ],
                          },
                        },
                  );
                  await refresh(page.id);
                })
              }
            >
              حفظ وسيلة الطلب
            </button>
            <button
              className={button}
              disabled={busy}
              onClick={() =>
                run(async () => {
                  setVerification(await verifyChannel(page.id));
                })
              }
            >
              التحقق قبل النشر
            </button>
            <button
              className={button}
              disabled={busy}
              onClick={() => run(async () => refresh(page.id))}
            >
              تحديث
            </button>
          </div>

          {jobId ? <p className="text-sm">مهمة التوليد: {jobId}</p> : null}
          {verification ? (
            <p
              className={`rounded-md px-3 py-2 text-sm ${
                verification.valid
                  ? "bg-emerald-50 text-emerald-700"
                  : "bg-amber-50 text-amber-800"
              }`}
            >
              {verification.valid
                ? "وسيلة الطلب جاهزة للنشر"
                : verification.errors.join(" · ")}
            </p>
          ) : null}

          {page.order_method?.whatsapp_link ? (
            <p className="text-sm">
              رابط واتساب:{" "}
              <a
                className="text-blue-700 underline"
                href={page.order_method.whatsapp_link}
                target="_blank"
                rel="noreferrer"
              >
                {page.order_method.whatsapp_link.slice(0, 90)}…
              </a>
            </p>
          ) : null}
          {page.order_method?.type === "cod" ? (
            <div className="text-sm">
              <p className="font-medium">حقول نموذج الدفع عند الاستلام:</p>
              <ul className="list-inside list-disc">
                {(
                  (page.order_method.cod_form_schema?.fields as
                    | { name: string; required?: boolean }[]
                    | undefined) ?? []
                ).map((entry) => (
                  <li key={entry.name}>
                    {entry.name} {entry.required ? "(مطلوب)" : ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {copy ? (
            <pre className="overflow-auto rounded-md bg-zinc-100 p-3 text-xs">
              {JSON.stringify(copy, null, 2)}
            </pre>
          ) : null}
          <pre className="overflow-auto rounded-md bg-zinc-100 p-3 text-xs">
            {JSON.stringify(page, null, 2)}
          </pre>
        </section>
      ) : null}
    </AppShell>
  );
}
