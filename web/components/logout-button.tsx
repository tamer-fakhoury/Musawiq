"use client";

import { useState } from "react";

import { logout } from "@/lib/auth";
import { useLanguage } from "@/lib/i18n";

export function LogoutButton() {
  const { t } = useLanguage();
  const [busy, setBusy] = useState(false);

  async function handleLogout() {
    if (busy) return;
    setBusy(true);
    try {
      await logout();
    } catch {
      // Even if the API call fails, clear local navigation state.
    } finally {
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign("/login");
    }
  }

  return (
    <button
      type="button"
      onClick={handleLogout}
      disabled={busy}
      className="rounded-md border border-zinc-300 px-3 py-2 text-base font-semibold text-zinc-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900 disabled:opacity-50"
    >
      {busy ? t("app.loggingOut") : t("app.logout")}
    </button>
  );
}
