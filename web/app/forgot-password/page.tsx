"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { requestPasswordReset } from "@/lib/auth";
import { LanguageSwitcher, useLanguage } from "@/lib/i18n";

const inputClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2.5 text-base text-zinc-950 outline-none focus-visible:border-zinc-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900";

export default function ForgotPasswordPage() {
  const { t } = useLanguage();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (!email.trim()) {
      setError(t("signup.emailInvalid"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await requestPasswordReset(email.trim());
      setSent(true);
    } catch {
      setError(t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-50 px-4 py-10">
      <div className="w-full max-w-md rounded-xl border border-zinc-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <h1 className="text-2xl font-semibold">{t("forgot.title")}</h1>
          <LanguageSwitcher />
        </div>

        {sent ? (
          <div className="mt-5 space-y-4">
            <p role="status" className="rounded-md bg-emerald-50 px-3 py-3 text-sm text-emerald-800">
              {t("forgot.success")}
            </p>
            <Link className="text-sm text-zinc-700 underline" href="/login">
              {t("forgot.back")}
            </Link>
          </div>
        ) : (
          <>
            <p className="mt-1 text-sm text-zinc-600">{t("forgot.subtitle")}</p>
            {error ? (
              <p role="alert" className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </p>
            ) : null}
            <form onSubmit={handleSubmit} className="mt-6 space-y-4" noValidate>
              <label className="block text-sm font-medium text-zinc-700" htmlFor="email">
                {t("forgot.email")}
                <input
                  id="email"
                  name="email"
                  type="email"
                  dir="ltr"
                  autoComplete="email"
                  className={inputClass}
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </label>
              <button
                type="submit"
                disabled={busy}
                className="w-full rounded-md bg-zinc-900 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
              >
                {busy ? t("forgot.submitting") : t("forgot.submit")}
              </button>
            </form>
            <Link className="mt-5 inline-block text-sm text-zinc-700 underline" href="/login">
              {t("forgot.back")}
            </Link>
          </>
        )}
      </div>
    </main>
  );
}
