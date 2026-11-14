"use client";

import Link from "next/link";
import { useState } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import {
  hasErrors,
  MIN_PASSWORD_LENGTH,
  type SignupErrors,
  type SignupFields,
  validateSignup,
} from "@/lib/auth-validation";
import { LanguageSwitcher, useLanguage } from "@/lib/i18n";

const inputClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2.5 text-base text-zinc-950 outline-none focus-visible:border-zinc-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900";

const INITIAL: SignupFields = {
  email: "",
  password: "",
  confirmPassword: "",
};

export default function SignupPage() {
  const { locale, t } = useLanguage();
  const [fields, setFields] = useState<SignupFields>(INITIAL);
  const [errors, setErrors] = useState<SignupErrors>({});
  const [touched, setTouched] = useState<
    Partial<Record<keyof SignupFields, boolean>>
  >({});
  const [busy, setBusy] = useState(false);
  const [serverError, setServerError] = useState("");
  const [correlationId, setCorrelationId] = useState("");
  const [createdEmail, setCreatedEmail] = useState("");
  const [resendBusy, setResendBusy] = useState(false);
  const [resendMessage, setResendMessage] = useState("");

  function update(field: keyof SignupFields, value: string) {
    const next = { ...fields, [field]: value };
    setFields(next);
    if (touched[field] || field === "confirmPassword") {
      setErrors(validateSignup(next, locale));
    }
    setServerError("");
  }

  function blur(field: keyof SignupFields) {
    setTouched((current) => ({ ...current, [field]: true }));
    setErrors(validateSignup(fields, locale));
  }

  function serverMessage(error: unknown): string {
    if (!(error instanceof ApiError)) return t("common.error");
    if (error.code === "signup_failed") {
      return locale === "ar"
        ? "تعذر إنشاء حساب بهذه البيانات."
        : "Unable to create an account with these details.";
    }
    if (error.code === "weak_password") return t("signup.passwordShort");
    if (error.code === "invalid_email") return t("signup.emailInvalid");
    return error.message;
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const nextErrors = validateSignup(fields, locale);
    setErrors(nextErrors);
    setTouched({ email: true, password: true, confirmPassword: true });
    if (hasErrors(nextErrors)) return;

    setBusy(true);
    setServerError("");
    setCorrelationId("");
    try {
      await apiFetch<{ status: string }>("/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: fields.email.trim(),
          password: fields.password,
        }),
      });
      setCreatedEmail(fields.email.trim());
      setFields(INITIAL);
    } catch (error) {
      setServerError(serverMessage(error));
      setCorrelationId(error instanceof ApiError ? error.correlationId : "");
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    if (resendBusy || !createdEmail) return;
    setResendBusy(true);
    setResendMessage("");
    try {
      await apiFetch("/auth/verify/resend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: createdEmail }),
      });
      setResendMessage(t("signup.resent"));
    } catch (error) {
      setResendMessage(serverMessage(error));
    } finally {
      setResendBusy(false);
    }
  }

  if (createdEmail) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-zinc-50 p-6">
        <section
          aria-labelledby="signup-success-title"
          className="w-full max-w-md rounded-xl border border-zinc-200 bg-white p-6 shadow-sm"
        >
          <div className="mb-4 flex justify-end">
            <LanguageSwitcher />
          </div>
          <h1 id="signup-success-title" className="text-2xl font-bold">
            {t("signup.successTitle")}
          </h1>
          <p className="mt-2 text-base font-medium text-zinc-600" dir="auto">
            {t("signup.successBody", { email: createdEmail })}
          </p>
          <button
            type="button"
            onClick={() => void resend()}
            disabled={resendBusy}
            className="mt-4 w-full rounded-md border border-zinc-300 px-3 py-2.5 text-base font-semibold disabled:opacity-50"
          >
            {resendBusy ? t("signup.resending") : t("signup.resend")}
          </button>
          {resendMessage ? (
            <p role="status" className="mt-3 text-base text-zinc-700">
              {resendMessage}
            </p>
          ) : null}
          <Link
            href="/login"
            className="mt-4 block text-center text-base font-semibold text-blue-700 underline"
          >
            {t("signup.goLogin")}
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-50 p-6">
      <section
        aria-labelledby="signup-title"
        className="w-full max-w-md rounded-xl border border-zinc-200 bg-white p-6 shadow-sm"
      >
        <div className="mb-4 flex justify-end">
          <LanguageSwitcher />
        </div>
        <h1 id="signup-title" className="text-2xl font-bold">
          {t("signup.title")}
        </h1>
        <p className="mt-1 text-base font-medium text-zinc-500">
          {t("signup.subtitle")}
        </p>

        {serverError ? (
          <div
            role="alert"
            className="mt-4 rounded-md bg-red-50 p-3 text-base text-red-800"
          >
            <p>{serverError}</p>
            {correlationId ? (
              <p className="mt-1 text-sm text-red-700" dir="ltr">
                Correlation ID: {correlationId}
              </p>
            ) : null}
          </div>
        ) : null}

        <form
          onSubmit={(event) => void submit(event)}
          noValidate
          className="mt-5 space-y-4"
        >
          <div>
            <label htmlFor="signup-email" className="text-base font-semibold">
              {t("signup.email")}
            </label>
            <input
              id="signup-email"
              type="email"
              value={fields.email}
              onChange={(event) => update("email", event.target.value)}
              onBlur={() => blur("email")}
              autoComplete="email"
              dir="ltr"
              aria-invalid={Boolean(errors.email)}
              aria-describedby={errors.email ? "signup-email-error" : undefined}
              className={inputClass}
            />
            {errors.email ? (
              <p
                id="signup-email-error"
                role="alert"
                className="mt-1 text-sm font-medium text-red-700"
              >
                {errors.email}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="signup-password" className="text-base font-semibold">
              {t("signup.password")}
            </label>
            <input
              id="signup-password"
              type="password"
              value={fields.password}
              onChange={(event) => update("password", event.target.value)}
              onBlur={() => blur("password")}
              autoComplete="new-password"
              minLength={MIN_PASSWORD_LENGTH}
              aria-invalid={Boolean(errors.password)}
              aria-describedby={
                errors.password ? "signup-password-error" : "signup-password-hint"
              }
              className={inputClass}
            />
            <p id="signup-password-hint" className="mt-1 text-sm text-zinc-500">
              {t("signup.hint")}
            </p>
            {errors.password ? (
              <p
                id="signup-password-error"
                role="alert"
                className="mt-1 text-sm font-medium text-red-700"
              >
                {errors.password}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="signup-confirm" className="text-base font-semibold">
              {t("signup.confirm")}
            </label>
            <input
              id="signup-confirm"
              type="password"
              value={fields.confirmPassword}
              onChange={(event) => update("confirmPassword", event.target.value)}
              onBlur={() => blur("confirmPassword")}
              autoComplete="new-password"
              aria-invalid={Boolean(errors.confirmPassword)}
              aria-describedby={
                errors.confirmPassword ? "signup-confirm-error" : undefined
              }
              className={inputClass}
            />
            {errors.confirmPassword ? (
              <p
                id="signup-confirm-error"
                role="alert"
                className="mt-1 text-sm font-medium text-red-700"
              >
                {errors.confirmPassword}
              </p>
            ) : null}
          </div>

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-md bg-zinc-900 px-3 py-2.5 text-base font-bold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900 disabled:opacity-50"
          >
            {busy ? t("signup.submitting") : t("signup.submit")}
          </button>
        </form>

        <p className="mt-5 text-center text-base font-medium text-zinc-600">
          {t("signup.haveAccount")}{" "}
          <Link href="/login" className="font-semibold text-blue-700 underline">
            {t("signup.login")}
          </Link>
        </p>
      </section>
    </main>
  );
}
