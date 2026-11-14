import type { Metadata } from "next";
import "./globals.css";

import { LanguageProvider } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "Musawiq — مساوق",
  description: "حلقة تحسين الإعلانات واختبار المنتجات.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ar" dir="rtl" className="h-full antialiased">
      <body className="min-h-full">
        <LanguageProvider>{children}</LanguageProvider>
      </body>
    </html>
  );
}
