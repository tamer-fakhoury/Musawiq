import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { HomeContent } from "@/components/home-content";

export default async function Home() {
  const session = (await cookies()).get("msq_session");
  if (!session?.value) {
    redirect("/login");
  }

  return (
    <AppShell>
      <HomeContent />
    </AppShell>
  );
}
