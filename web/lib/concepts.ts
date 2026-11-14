import { formatCurrency, formatDate as formatDateLocale } from "@/lib/i18n";

export type ConceptStatus = "draft" | "evaluated" | "selected" | "archived";

export type Concept = {
  id: string;
  store_id: string;
  name: string;
  description: string | null;
  category_id: string;
  niche_id: string | null;
  price_minor: number;
  cost_minor: number;
  currency: string;
  gross_margin_bp: number;
  gross_margin_percent: number;
  is_negative_margin: boolean;
  image_file_id: string | null;
  status: ConceptStatus;
  version: number;
  latest_evaluation_id: string | null;
  latest_score: number | null;
  latest_score_scale: number | null;
  latest_confidence: string | null;
  latest_is_reliable: boolean | null;
  latest_evaluated_at: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type Category = {
  id: string;
  parent_id: string | null;
  name: string;
  slug: string;
  sort_order: number;
};

export const CONCEPT_STATUSES: ConceptStatus[] = [
  "draft",
  "evaluated",
  "selected",
  "archived",
];

export const STATUS_LABELS: Record<ConceptStatus, string> = {
  draft: "مسودة",
  evaluated: "تم التقييم",
  selected: "مختار",
  archived: "مؤرشف",
};

export const SORT_OPTIONS = [
  { value: "created_at", label: "تاريخ الإنشاء" },
  { value: "score", label: "أحدث درجة" },
  { value: "category", label: "الفئة" },
] as const;

export function statusLabel(value: string): string {
  return STATUS_LABELS[value as ConceptStatus] ?? value;
}

export function formatMoney(minor: number, currency: string): string {
  return formatCurrency(minor, currency);
}

export function formatDate(value: string | null): string {
  return formatDateLocale(value);
}

export function formatScore(concept: Concept): string {
  if (concept.latest_score === null) {
    return "—";
  }
  const scale = concept.latest_score_scale ?? 100;
  return `${concept.latest_score.toFixed(1)} / ${scale}`;
}
