import type { Concept } from "@/lib/concepts";

export type ComparisonFactor = {
  factor_key: string;
  factor_label: string;
  direction: "positive" | "negative" | "neutral";
  contribution: number;
  explanation: string;
  evidence: Record<string, unknown>;
};

export type ComparisonConcept = {
  concept_id: string;
  name: string;
  status: string;
  category_id: string;
  category: string | null;
  price_minor: number;
  cost_minor: number;
  currency: string;
  gross_margin_bp: number;
  gross_margin_percent: number;
  evaluation_id: string;
  score: number | null;
  score_scale: number;
  confidence: string;
  is_reliable: boolean;
  evaluated_at: string;
  top_factors: ComparisonFactor[];
};

export type ComparisonResult = {
  concepts: ComparisonConcept[];
  count: number;
};

export type SelectionResult = {
  selected_ids: string[];
  concepts: Concept[];
};
