"use client";

import Link from "next/link";
import { useRef, useState, type FormEvent } from "react";

import { ApiError } from "@/lib/api";
import { login, resendVerification } from "@/lib/auth";
import { LanguageSwitcher, useLanguage } from "@/lib/i18n";

const inputClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2.5 text-base text-zinc-950 outline-none focus-visible:border-zinc-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900";

function safeNext(): string | null {
  if (typeof window === "undefined") return null;
  const next = new URLSearchParams(window.location.search).get("next");
  if (!next || !next.startsWith("/") || next.startsWith("//")) return null;
  return next;
}

export default function LoginPage() {
  const { locale, t } = useLanguage();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [formError, setFormError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{
    email?: string;
    password?: string;
  }>({});
  const [submitting, setSubmitting] = useState(false);
  const [unverified, setUnverified] = useState(false);
  const [resendState, setResendState] = useState<"idle" | "sending" | "sent">(
    "idle",
  );
  const inFlight = useRef(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current || submitting) return;

    const errors: { email?: string; password?: string } = {};
    if (!email.trim()) {
      errors.email =
        locale === "ar" ? "البريد الإلكتروني مطلوب." : "Email is required.";
    }
    if (!password) {
      errors.password =
        locale === "ar" ? "كلمة المرور مطلوبة." : "Password is required.";
    }
    setFieldErrors(errors);
    setFormError("");
    setUnverified(false);
    if (Object.keys(errors).length > 0) return;

    inFlight.current = true;
    setSubmitting(true);
    try {
      const result = await login(email.trim(), password);
      const target = result.active_store
        ? safeNext() ?? "/"
        : "/onboarding/store";
      window.location.assign(target);
    } catch (cause) {
      if (cause instanceof ApiError) {
        if (cause.status === 401) {
          setFormError(t("login.invalid"));
        } else if (cause.status === 403 && cause.code === "email_unverified") {
          setUnverified(true);
          setFormError(t("login.unverified"));
        } else if (cause.status === 429) {
          setFormError(t("login.rateLimited"));
        } else {
          setFormError(cause.message || t("common.error"));
        }
      } else {
        setFormError(t("common.error"));
      }
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  }

  async function handleResend() {
    if (!email.trim() || resendState === "sending") return;
    setResendState("sending");
    try {
      await resendVerification(email.trim());
      setResendState("sent");
    } catch {
      setResendState("idle");
      setFormError(t("common.error"));
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-50 px-4 py-10">
      <div className="w-full max-w-md rounded-xl border border-zinc-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex justify-end">
          <LanguageSwitcher />
        </div>
        <h1 className="text-2xl font-bold">{t("login.title")}</h1>
        <p className="mt-1 text-base font-medium text-zinc-500">
          {t("login.subtitle")}
        </p>

        {formError ? (
          <div
            role="alert"
            className="mt-4 rounded-md bg-red-50 px-3 py-2 text-base text-red-700"
          >
            <p>{formError}</p>
            {unverified ? (
              <button
                type="button"
                onClick={() => void handleResend()}
                disabled={resendState === "sending"}
                className="mt-2 rounded-md border border-red-300 px-3 py-1.5 text-base font-semibold text-red-800 disabled:opacity-50"
              >
                {resendState === "sent"
                  ? t("login.resent")
                  : resendState === "sending"
                    ? t("login.resending")
                    : t("login.resend")}
              </button>
            ) : null}
          </div>
        ) : null}

        <form onSubmit={handleSubmit} className="mt-6 space-y-4" noValidate>
          <label className="block text-base font-semibold text-zinc-700" htmlFor="email">
            {t("login.email")}
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              dir="ltr"
              className={inputClass}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={Boolean(fieldErrors.email)}
              aria-describedby={fieldErrors.email ? "email-error" : undefined}
              required
            />
          </label>
          {fieldErrors.email ? (
            <p id="email-error" role="alert" className="text-sm font-medium text-red-700">
              {fieldErrors.email}
            </p>
          ) : null}

          <label className="block text-base font-semibold text-zinc-700" htmlFor="password">
            {t("login.password")}
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              dir="ltr"
              className={inputClass}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={Boolean(fieldErrors.password)}
              aria-describedby={
                fieldErrors.password ? "password-error" : undefined
              }
              required
            />
          </label>
          {fieldErrors.password ? (
            <p
              id="password-error"
              role="alert"
              className="text-sm font-medium text-red-700"
            >
              {fieldErrors.password}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-zinc-900 px-3 py-2.5 text-base font-bold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900 disabled:opacity-50"
          >
            {submitting ? t("login.submitting") : t("login.submit")}
          </button>
        </form>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-2 text-base font-medium">
          <Link href="/forgot-password" className="text-blue-700 underline">
            {t("login.forgot")}
          </Link>
          <p className="text-zinc-600">
            {t("login.noAccount")}{" "}
            <Link href="/signup" className="font-semibold text-blue-700 underline">
              {t("login.createAccount")}
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}
