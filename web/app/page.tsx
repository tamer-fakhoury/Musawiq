import { AppShell } from "@/components/app-shell";

export default function Home() {
  return (
    <AppShell>
      <section className="rounded-lg border border-dashed border-zinc-300 p-10 text-center">
        <h1 className="text-base font-semibold">No data yet</h1>
        <p className="mt-2 text-sm text-zinc-500">
          Modules will appear here as they become available.
        </p>
      </section>
    </AppShell>
  );
}
