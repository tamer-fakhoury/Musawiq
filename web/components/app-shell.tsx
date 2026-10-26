import Link from "next/link";
import type { ReactNode } from "react";

const NAV_ITEMS = [
  "لوحة التحكم",
  "الاستيراد",
  "الجمهور",
  "المفاهيم",
  "التوصيات",
  "الصفحات",
  "الحملات",
  "الحكم",
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="flex items-center justify-between border-b border-zinc-200 px-6 py-4">
        <span className="text-lg font-semibold tracking-tight">Musawiq</span>
        <span className="text-sm text-zinc-500">حلقة تحسين الإعلانات</span>
      </header>
      <div className="flex flex-1">
        <nav
          aria-label="التنقل الرئيسي"
          className="w-56 shrink-0 border-e border-zinc-200 p-4"
        >
          <ul className="space-y-1">
            {NAV_ITEMS.map((item) => (
              <li key={item}>
                {item === "الحملات" ? (
                  <Link
                    href="/campaigns"
                    className="block w-full rounded-md bg-zinc-900 px-3 py-2 text-start text-sm font-medium text-white"
                  >
                    {item}
                  </Link>
                ) : (
                  <button
                    type="button"
                    disabled
                    className="w-full rounded-md px-3 py-2 text-start text-sm text-zinc-400"
                  >
                    {item}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </nav>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
