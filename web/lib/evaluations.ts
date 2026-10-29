export type EvaluationFactor = {
  id: string;
  factor_key: string;
  factor_label: string;
  direction: "positive" | "negative" | "neutral";
  contribution: number;
  explanation: string;
  evidence: {
    schema_version?: number;
    source?: "measured" | "inferred";
    factor_value?: number;
  };
};

export type Evaluation = {
  id: string;
  product_concept_id: string;
  scoring_model_id: string;
  model_version: number;
  score: number | null;
  score_scale: number;
  confidence: "high" | "medium" | "low";
  is_reliable: boolean;
  sufficiency_check_id: string | null;
  input_snapshot: Record<string, unknown>;
  evaluated_at: string;
  factors: EvaluationFactor[];
};

export type ExplainedFactor = {
  factor_key: string;
  factor_label: string;
  direction: "positive" | "negative" | "neutral";
  contribution: number;
  explanation: string;
  evidence_label: "measured" | "inferred";
};

export type Explanation = {
  evaluation_id: string;
  product_concept_id: string;
  score: number | null;
  score_scale: number;
  confidence: "high" | "medium" | "low";
  is_reliable: boolean;
  summary: string;
  top_positive: ExplainedFactor[];
  top_negative: ExplainedFactor[];
  factors: ExplainedFactor[];
  limitations: string[];
  measured_inputs: string[];
  inferred_inputs: string[];
  sufficiency_check: {
    id: string;
    overall_status: string;
    blocking_reasons: string[];
    checked_at: string;
  } | null;
};

export const CONFIDENCE_LABELS: Record<string, string> = {
  high: "عالية",
  medium: "متوسطة",
  low: "منخفضة",
};

export function confidenceLabel(value: string): string {
  return CONFIDENCE_LABELS[value] ?? value;
}

export function formatScore(score: number | null, scale: number): string {
  return score === null ? "غير متاح" : `${score.toFixed(1)} / ${scale}`;
}

export function factorSourceLabel(value: string): string {
  return value === "inferred" ? "مستنتج" : "مقاس";
}
