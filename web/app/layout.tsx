import type { Metadata } from "next";
import { cookies } from "next/headers";

import "./globals.css";

import { LanguageProvider } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "Musawiq — مساوق",
  description: "حلقة تحسين الإعلانات واختبار المنتجات.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const store = await cookies();
  const locale = store.get("msq_locale")?.value === "en" ? "en" : "ar";
  const direction = locale === "ar" ? "rtl" : "ltr";

  return (
    <html
      lang={locale}
      dir={direction}
      className="h-full antialiased"
      suppressHydrationWarning
    >
      <body className="min-h-full">
        <LanguageProvider>{children}</LanguageProvider>
      </body>
    </html>
  );
}
