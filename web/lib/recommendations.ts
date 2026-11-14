import { formatDate as formatDateLocale } from "@/lib/i18n";

export type GenerationRun = {
  id: string;
  requested_by: string;
  model_version: string;
  input_snapshot: Record<string, unknown>;
  requested_count: number;
  returned_count: number;
  status: "queued" | "running" | "succeeded" | "failed";
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

export type IdeaEvidence = {
  id: string;
  evidence_type: "verified" | "hypothesis";
  label: string;
  claim: string;
  source_name: string | null;
  source_url: string | null;
  source_published_at: string | null;
  retrieved_at: string | null;
  confidence: number | null;
  is_stale: boolean;
};

export type ProductIdea = {
  id: string;
  generation_run_id: string;
  name: string;
  description: string;
  category_id: string | null;
  niche_id: string | null;
  rationale: string;
  state: "new" | "saved" | "dismissed" | "converted";
  dismissed_reason: string | null;
  converted_concept_id: string | null;
  model_version: string;
  created_at: string;
  updated_at: string;
  evidence: IdeaEvidence[];
};

export const RUN_STATUS_LABELS: Record<string, string> = {
  queued: "في الانتظار",
  running: "قيد التشغيل",
  succeeded: "مكتمل",
  failed: "فشل",
};

export const IDEA_STATE_LABELS: Record<string, string> = {
  new: "جديد",
  saved: "محفوظ",
  dismissed: "مستبعد",
  converted: "محوّل",
};

export function runStatusLabel(value: string): string {
  return RUN_STATUS_LABELS[value] ?? value;
}

export function ideaStateLabel(value: string): string {
  return IDEA_STATE_LABELS[value] ?? value;
}

export function formatDate(value: string | null): string {
  return formatDateLocale(value);
}
