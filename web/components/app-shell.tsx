import type { ReactNode } from "react";

const NAV_ITEMS = [
  "Dashboard",
  "Import",
  "Audience",
  "Concepts",
  "Recommendations",
  "Pages",
  "Campaigns",
  "Verdict",
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="border-b border-zinc-200 px-6 py-4">
        <span className="text-lg font-semibold tracking-tight">Musawiq</span>
      </header>
      <div className="flex flex-1">
        <nav
          aria-label="Primary"
          className="w-56 shrink-0 border-r border-zinc-200 p-4"
        >
          <ul className="space-y-1">
            {NAV_ITEMS.map((item) => (
              <li key={item}>
                <button
                  type="button"
                  disabled
                  className="w-full rounded-md px-3 py-2 text-left text-sm text-zinc-400"
                >
                  {item}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
