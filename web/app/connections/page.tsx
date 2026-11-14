"use client";

import { useEffect, useState, type FormEvent } from "react";

import { AppShell } from "@/components/app-shell";
import { ApiError, apiFetch } from "@/lib/api";

const fieldClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900";
const labelClass = "block text-sm font-medium text-zinc-700";
const PROVIDERS = ["meta", "tiktok", "google", "snapchat"] as const;

type Connection = {
  id: string;
  provider: string;
  external_account_id: string;
  account_name: string | null;
  status: string;
  scopes: string[];
  token_expires_at: string | null;
  is_expired: boolean;
  last_synced_at: string | null;
};

function errorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

export default function ConnectionsPage() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [provider, setProvider] = useState<string>("meta");
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [stateValue, setStateValue] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadConnections() {
    setConnections(
      await apiFetch<Connection[]>("/campaigns/ad-accounts"),
    );
  }

  useEffect(() => {
    let active = true;
    apiFetch<Connection[]>("/campaigns/ad-accounts")
      .then((data) => {
        if (active) setConnections(data);
      })
      .catch((loadError) => {
        if (active) setError(errorMessage(loadError, "تعذر تحميل الاتصالات."));
      });
    return () => {
      active = false;
    };
  }, []);

  async function authorize() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const data = await apiFetch<{
        authorization_url: string;
        state: string;
      }>("/campaigns/ad-accounts/authorize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider }),
      });
      setAuthUrl(data.authorization_url);
      setStateValue(data.state);
      setNotice("افتح رابط التفويض ثم الصق رمز التفويض هنا.");
    } catch (authError) {
      setError(errorMessage(authError, "تعذر بدء OAuth."));
    } finally {
      setBusy(false);
    }
  }

  async function complete(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiFetch<Connection>("/campaigns/ad-accounts/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, code, state: stateValue }),
      });
      setNotice("تم ربط الحساب.");
      setAuthUrl(null);
      setCode("");
      await loadConnections();
    } catch (completeError) {
      setError(errorMessage(completeError, "تعذر إكمال OAuth."));
    } finally {
      setBusy(false);
    }
  }

  async function refresh(connection: Connection) {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/campaigns/ad-accounts/${connection.id}/refresh`, {
        method: "POST",
      });
      await loadConnections();
      setNotice("تم تحديث الرمز.");
    } catch (refreshError) {
      setError(errorMessage(refreshError, "تعذر تحديث الرمز."));
    } finally {
      setBusy(false);
    }
  }

  async function disconnect(connection: Connection) {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/campaigns/ad-accounts/${connection.id}/disconnect`, {
        method: "POST",
      });
      await loadConnections();
      setNotice("تم فصل الحساب.");
    } catch (disconnectError) {
      setError(errorMessage(disconnectError, "تعذر فصل الحساب."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold">اتصالات الحسابات الإعلانية</h1>
          <p className="mt-1 text-sm text-zinc-500">
            يستخدم OAuth الحقيقي فقط. لا توجد محولات تجريبية.
          </p>
        </div>
        {error ? <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
        {notice ? <p role="status" className="rounded-md bg-green-50 p-3 text-sm text-green-700">{notice}</p> : null}

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-base font-semibold">ربط حساب</h2>
          <div className="mt-4 flex flex-wrap items-end gap-3">
            <div>
              <label className={labelClass} htmlFor="provider">المنصة</label>
              <select id="provider" value={provider} onChange={(event) => setProvider(event.target.value)} className={fieldClass}>
                {PROVIDERS.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
            <button type="button" onClick={() => void authorize()} disabled={busy} className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">بدء OAuth</button>
          </div>
          {authUrl ? (
            <p className="mt-3 break-all text-sm">
              <a href={authUrl} target="_blank" rel="noreferrer" className="text-blue-700 underline">فتح رابط التفويض</a>
            </p>
          ) : null}
          <form onSubmit={complete} className="mt-4 grid gap-3 md:grid-cols-2">
            <div>
              <label className={labelClass} htmlFor="auth-code">رمز التفويض (code)</label>
              <input id="auth-code" value={code} onChange={(event) => setCode(event.target.value)} className={fieldClass} dir="ltr" />
            </div>
            <div>
              <label className={labelClass} htmlFor="auth-state">الحالة</label>
              <input id="auth-state" value={stateValue} onChange={(event) => setStateValue(event.target.value)} className={fieldClass} dir="ltr" />
            </div>
            <div className="flex items-end">
              <button type="submit" disabled={busy || !code || !stateValue} className="rounded-md border border-zinc-300 px-4 py-2 text-sm">إكمال الربط</button>
            </div>
          </form>
        </section>

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-base font-semibold">الحسابات المرتبطة</h2>
          <ul className="mt-3 divide-y divide-zinc-200">
            {connections.map((connection) => (
              <li key={connection.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div>
                  <p className="text-sm font-medium">{connection.provider} • {connection.account_name ?? connection.external_account_id}</p>
                  <p className="text-xs text-zinc-500">{connection.status}{connection.is_expired ? " • منتهي" : ""} • {connection.scopes.join(", ")}</p>
                </div>
                <div className="flex gap-2">
                  <button type="button" disabled={busy} onClick={() => void refresh(connection)} className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm">تحديث</button>
                  <button type="button" disabled={busy} onClick={() => void disconnect(connection)} className="rounded-md border border-red-200 px-3 py-1.5 text-sm text-red-700">فصل</button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </AppShell>
  );
}
