"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

type PublicPage = {
  slug: string;
  language: string;
  direction: string;
  currency: string;
  published_at: string | null;
  content: {
    product?: {
      name?: string;
      description?: string | null;
      price_minor?: number;
      currency?: string;
      target_market?: string;
    };
    order_method?: {
      type?: string;
      whatsapp_link?: string | null;
    } | null;
  };
};

export default function PublicLandingPage() {
  const params = useParams<{ slug: string }>();
  const [page, setPage] = useState<PublicPage | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "missing">(
    "loading",
  );

  useEffect(() => {
    let active = true;
    async function load() {
      await Promise.resolve();
      if (!active) return;
      const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
      if (!baseUrl || !params.slug) {
        setState("missing");
        return;
      }
      try {
        const response = await fetch(
          `${baseUrl}/p/${encodeURIComponent(params.slug)}`,
          { cache: "no-store" },
        );
        if (!active) return;
        if (!response.ok) {
          setState("missing");
          return;
        }
        setPage(await response.json());
        setState("ready");
      } catch {
        if (active) setState("missing");
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [params.slug]);

  if (state === "loading") {
    return <main className="p-8 text-sm text-zinc-500">جارٍ التحميل…</main>;
  }
  if (state === "missing" || !page) {
    return <main className="p-8 text-sm text-zinc-600">هذه الصفحة غير متاحة.</main>;
  }

  const product = page.content.product ?? {};
  const price =
    typeof product.price_minor === "number"
      ? `${(product.price_minor / 100).toFixed(2)} ${product.currency ?? page.currency}`
      : null;
  const order = page.content.order_method;
  const whatsappPath = order?.whatsapp_link;
  const whatsappHref = whatsappPath
    ? whatsappPath.startsWith("http")
      ? whatsappPath
      : `${process.env.NEXT_PUBLIC_API_BASE_URL ?? ""}${whatsappPath}`
    : null;

  return (
    <main
      dir={page.direction || "rtl"}
      lang={page.language}
      className="mx-auto min-h-screen max-w-3xl p-6"
    >
      <h1 className="text-3xl font-semibold">{product.name ?? page.slug}</h1>
      {product.description ? (
        <p className="mt-4 whitespace-pre-line text-zinc-700">
          {product.description}
        </p>
      ) : null}
      {price ? <p className="mt-6 text-2xl font-semibold">{price}</p> : null}
      {whatsappHref ? (
        <a
          href={whatsappHref}
          data-msq-cta
          className="mt-8 inline-block rounded-md bg-zinc-900 px-5 py-3 text-white"
        >
          اطلب عبر واتساب
        </a>
      ) : null}
    </main>
  );
}
