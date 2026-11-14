"use client";

import Link from "next/link";

import { useI18n } from "@/lib/i18n";

export function HomeContent() {
  const { t } = useI18n();
  return (
    <section className="rounded-lg border border-dashed border-zinc-300 p-10 text-center">
      <h1 className="text-xl font-bold">{t("home.title")}</h1>
      <p className="mt-2 text-base font-medium text-zinc-500">
        {t("home.body")}
      </p>
      <Link
        href="/campaigns"
        className="mt-5 inline-block rounded-md bg-zinc-900 px-4 py-2.5 text-base font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
      >
        {t("home.cta")}
      </Link>
    </section>
  );
}
