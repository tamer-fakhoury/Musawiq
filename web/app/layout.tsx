import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Musawiq — مساوق",
  description: "منصة اختبار المنتجات وتحسين الحملات الإعلانية",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ar" dir="rtl" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
