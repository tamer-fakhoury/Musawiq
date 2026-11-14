type HealthState = "ok" | "degraded" | "unreachable";

type HealthCheck = {
  state: HealthState;
  status: number | null;
};

async function checkHealth(): Promise<HealthCheck> {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!baseUrl) {
    return { state: "unreachable", status: null };
  }

  try {
    const response = await fetch(`${baseUrl}/health`, { cache: "no-store" });
    return {
      state: response.ok ? "ok" : "degraded",
      status: response.status,
    };
  } catch {
    return { state: "unreachable", status: null };
  }
}

export const dynamic = "force-dynamic";

export default async function HealthPage() {
  const { state, status } = await checkHealth();

  return (
    <main className="p-8">
      <h1 className="text-lg font-semibold">حالة الخدمة</h1>
      <p className="mt-4 text-sm">
        Status: <strong>{state}</strong>
      </p>
      <p className="mt-1 text-sm">HTTP status: {status ?? "—"}</p>
    </main>
  );
}
