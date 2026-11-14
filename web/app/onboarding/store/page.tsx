"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import { LanguageSwitcher, useLanguage } from "@/lib/i18n";

const inputClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2.5 text-base text-zinc-950 outline-none focus-visible:border-zinc-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900";

type StoreForm = {
  name: string;
  default_currency: string;
  default_language: string;
  timezone: string;
  country_code: string;
};

const INITIAL: StoreForm = {
  name: "",
  default_currency: "SAR",
  default_language: "ar",
  timezone: "Asia/Riyadh",
  country_code: "SA",
};

const FIELD_BY_CODE: Record<string, keyof StoreForm> = {
  invalid_name: "name",
  invalid_default_currency: "default_currency",
  invalid_default_language: "default_language",
  invalid_timezone: "timezone",
  invalid_country_code: "country_code",
  slug_unavailable: "name",
};

function readCsrf(): string {
  const stored = window.sessionStorage.getItem("msq_csrf");
  if (stored) return stored;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith("msq_csrf="));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

export default function OnboardingStorePage() {
  const router = useRouter();
  const { t } = useLanguage();
  const [form, setForm] = useState<StoreForm>(INITIAL);
  const [errors, setErrors] = useState<Partial<Record<keyof StoreForm, string>>>(
    {},
  );
  const [serverError, setServerError] = useState("");
  const [correlationId, setCorrelationId] = useState("");
  const [needsLogin, setNeedsLogin] = useState(false);
  const [busy, setBusy] = useState(false);

  function update(field: keyof StoreForm, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
    setServerError("");
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const name = form.name.trim();
    if (!name) {
      setErrors({ name: t("onboarding.nameRequired") });
      return;
    }
    const csrf = readCsrf();
    if (!csrf) {
      setNeedsLogin(true);
      setServerError(t("onboarding.sessionExpired"));
      return;
    }

    setBusy(true);
    setServerError("");
    setCorrelationId("");
    setNeedsLogin(false);
    try {
      await apiFetch("/auth/onboarding/store", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf,
        },
        body: JSON.stringify({
          name,
          default_currency: form.default_currency.trim().toUpperCase(),
          default_language: form.default_language.trim().toLowerCase(),
          timezone: form.timezone.trim(),
          country_code: form.country_code.trim().toUpperCase(),
        }),
      });
      router.replace("/");
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 401 || error.code === "not_eligible") {
          router.replace("/login");
          return;
        }
        setServerError(error.message);
        setCorrelationId(error.correlationId);
        setNeedsLogin(error.code === "csrf_invalid");
        const field = FIELD_BY_CODE[error.code];
        if (field) {
          setErrors({ [field]: error.message });
        }
      } else {
        setServerError(t("onboarding.failed"));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-50 p-6">
      <section
        aria-labelledby="onboarding-title"
        className="w-full max-w-lg rounded-xl border border-zinc-200 bg-white p-6 shadow-sm"
      >
        <div className="mb-4 flex justify-end">
          <LanguageSwitcher />
        </div>
        <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500">
          {t("onboarding.step")}
        </p>
        <h1 id="onboarding-title" className="mt-1 text-2xl font-bold">
          {t("onboarding.title")}
        </h1>
        <p className="mt-1 text-base font-medium text-zinc-500">
          {t("onboarding.subtitle")}
        </p>

        {serverError ? (
          <div
            role="alert"
            className="mt-4 rounded-md bg-red-50 p-3 text-base text-red-800"
          >
            <p>{serverError}</p>
            {correlationId ? (
              <p className="mt-1 text-sm text-red-700" dir="ltr">
                معرّف الارتباط: {correlationId}
              </p>
            ) : null}
            {needsLogin ? (
              <Link
                href="/login"
                className="mt-2 inline-block font-semibold underline"
              >
                {t("onboarding.loginAgain")}
              </Link>
            ) : null}
          </div>
        ) : null}

        <form
          onSubmit={(event) => void submit(event)}
          noValidate
          className="mt-5 space-y-4"
        >
          <div>
            <label htmlFor="store-name" className="text-base font-semibold">
              {t("onboarding.name")}
            </label>
            <input
              id="store-name"
              value={form.name}
              onChange={(event) => update("name", event.target.value)}
              aria-invalid={Boolean(errors.name)}
              aria-describedby={errors.name ? "store-name-error" : undefined}
              className={inputClass}
            />
            {errors.name ? (
              <p
                id="store-name-error"
                role="alert"
                className="mt-1 text-sm font-medium text-red-700"
              >
                {errors.name}
              </p>
            ) : null}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="store-currency" className="text-base font-semibold">
                {t("onboarding.currency")}
              </label>
              <input
                id="store-currency"
                value={form.default_currency}
                onChange={(event) =>
                  update("default_currency", event.target.value)
                }
                maxLength={3}
                dir="ltr"
                className={inputClass}
              />
              {errors.default_currency ? (
                <p role="alert" className="mt-1 text-sm font-medium text-red-700">
                  {errors.default_currency}
                </p>
              ) : null}
            </div>
            <div>
              <label htmlFor="store-language" className="text-base font-semibold">
                {t("onboarding.language")}
              </label>
              <input
                id="store-language"
                value={form.default_language}
                onChange={(event) =>
                  update("default_language", event.target.value)
                }
                maxLength={10}
                dir="ltr"
                className={inputClass}
              />
              {errors.default_language ? (
                <p role="alert" className="mt-1 text-sm font-medium text-red-700">
                  {errors.default_language}
                </p>
              ) : null}
            </div>
            <div>
              <label htmlFor="store-timezone" className="text-base font-semibold">
                {t("onboarding.timezone")}
              </label>
              <input
                id="store-timezone"
                value={form.timezone}
                onChange={(event) => update("timezone", event.target.value)}
                dir="ltr"
                className={inputClass}
              />
              {errors.timezone ? (
                <p role="alert" className="mt-1 text-sm font-medium text-red-700">
                  {errors.timezone}
                </p>
              ) : null}
            </div>
            <div>
              <label htmlFor="store-country" className="text-base font-semibold">
                {t("onboarding.country")}
              </label>
              <input
                id="store-country"
                value={form.country_code}
                onChange={(event) => update("country_code", event.target.value)}
                maxLength={2}
                dir="ltr"
                className={inputClass}
              />
              {errors.country_code ? (
                <p role="alert" className="mt-1 text-sm font-medium text-red-700">
                  {errors.country_code}
                </p>
              ) : null}
            </div>
          </div>

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-md bg-zinc-900 px-3 py-2.5 text-base font-bold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900 disabled:opacity-50"
          >
            {busy ? t("onboarding.submitting") : t("onboarding.submit")}
          </button>
        </form>
      </section>
    </main>
  );
}
