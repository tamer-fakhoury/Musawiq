import Link from "next/link";
import type { ReactNode } from "react";

import { LogoutButton } from "@/components/logout-button";
import {
  LanguageSwitcher,
  useLanguage,
  type MessageKey,
} from "@/lib/i18n";

const NAV_ITEMS: Array<{ key: MessageKey; href: string }> = [
  { key: "nav.dashboard", href: "/" },
  { key: "nav.imports", href: "/imports" },
  { key: "nav.audiences", href: "/audiences" },
  { key: "nav.feedback", href: "/feedback" },
  { key: "nav.concepts", href: "/concepts" },
  { key: "nav.evaluations", href: "/evaluations" },
  { key: "nav.compare", href: "/compare" },
  { key: "nav.recommendations", href: "/recommendations" },
  { key: "nav.landingPages", href: "/landing-pages" },
  { key: "nav.campaigns", href: "/campaigns" },
  { key: "nav.connections", href: "/connections" },
  { key: "nav.operations", href: "/operations" },
  { key: "nav.metrics", href: "/metrics" },
  { key: "nav.verdicts", href: "/verdicts" },
  { key: "nav.investment", href: "/investment" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useLanguage();

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 px-4 py-4 sm:px-6">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold tracking-tight">Musawiq</span>
          <span className="text-base font-medium text-zinc-500">
            {t("app.subtitle")}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <LanguageSwitcher />
          <LogoutButton />
        </div>
      </header>
      <div className="flex flex-1 flex-col md:flex-row">
        <nav
          aria-label={t("nav.label")}
          className="w-full shrink-0 border-b border-zinc-200 p-3 md:w-64 md:border-b-0 md:border-e md:p-4"
        >
          <ul className="grid grid-cols-2 gap-1 sm:grid-cols-3 md:grid-cols-1">
            {NAV_ITEMS.map((item) => (
              <li key={item.key}>
                <Link
                  href={item.href}
                  className="block w-full rounded-md bg-zinc-900 px-3 py-2.5 text-start text-base font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
                >
                  {t(item.key)}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <main className="flex-1 p-4 text-base sm:p-6">{children}</main>
      </div>
    </div>
  );
}
