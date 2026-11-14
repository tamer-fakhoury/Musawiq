import { formatDate as formatDateLocale } from "@/lib/i18n";

export type FeedbackSource = "manual" | "file";
export type FeedbackSentiment = "positive" | "neutral" | "negative";

export type FeedbackItem = {
  id: string;
  store_id: string;
  audience_profile_id: string | null;
  source: FeedbackSource;
  stored_file_id: string | null;
  text: string;
  language: string | null;
  sentiment: FeedbackSentiment | null;
  captured_at: string;
  created_at: string;
};

export const SENTIMENT_LABELS: Record<FeedbackSentiment, string> = {
  positive: "إيجابي",
  neutral: "محايد",
  negative: "سلبي",
};

export function sentimentLabel(value: string | null): string {
  if (!value) {
    return "غير محدد";
  }
  return SENTIMENT_LABELS[value as FeedbackSentiment] ?? value;
}

export function sourceLabel(value: string): string {
  return value === "file" ? "ملف" : "إدخال يدوي";
}

export function formatDate(value: string): string {
  return formatDateLocale(value);
}
