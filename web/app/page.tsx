import Link from "next/link";

import { AppShell } from "@/components/app-shell";

export default function Home() {
  return (
    <AppShell>
      <section className="rounded-lg border border-dashed border-zinc-300 p-10 text-center">
        <h1 className="text-base font-semibold">لا توجد بيانات بعد</h1>
        <p className="mt-2 text-sm text-zinc-500">
          ابدأ بإنشاء حملة إعلانية لتسجيل الإشارات وتحليلها.
        </p>
        <Link
          href="/campaigns"
          className="mt-5 inline-block rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white"
        >
          الانتقال إلى الحملات
        </Link>
      </section>
    </AppShell>
  );
}
