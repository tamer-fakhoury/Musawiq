export type DemandLevel = "strong" | "moderate" | "weak" | "inconclusive";
export type IssueType =
  | "content"
  | "channel"
  | "targeting"
  | "budget"
  | "audience";
export type Severity = "low" | "medium" | "high";
export type RecommendationAction =
  | "keep"
  | "pause"
  | "increase_budget"
  | "decrease_budget"
  | "change_copy"
  | "change_creative"
  | "change_targeting";
export type AnalysisStatus = "succeeded" | "degraded" | "failed";

export type Demand = {
  level: DemandLevel;
  confidence: number;
  rationale_ar: string;
};

export type Issue = {
  type: IssueType;
  severity: Severity;
  metric: string;
  observed: number;
  benchmark: number | string;
  rationale_ar: string;
};

export type Recommendation = {
  action: RecommendationAction;
  target: string;
  change_ar: string;
  expected_impact_ar: string;
  confidence: number;
  copy_paste_ar: string;
};

export type DeltaDirection = "improved" | "degraded" | "flat";

export type MetricDelta = {
  metric: string;
  before: number | null;
  after: number | null;
  change_abs: number | null;
  change_pct: number | null;
  direction: DeltaDirection;
};

export type DeltaSummary = {
  improved: number;
  degraded: number;
  flat: number;
  headline: DeltaDirection | "mixed";
};

export type AnalysisDelta = {
  deltas: MetricDelta[];
  summary: DeltaSummary;
};

export type AnalysisResult = {
  demand: Demand;
  issues: Issue[];
  recommendations: Recommendation[];
  next_steps_ar: string[];
  delta?: AnalysisDelta | null;
};

export type AnalysisFailure = {
  degraded_reason?: string;
  error?: string;
};

export type Analysis = {
  id: string;
  campaign_id: string;
  parent_analysis_id: string | null;
  window_start: string | null;
  window_end: string | null;
  status: AnalysisStatus;
  provider: string;
  model_version: string;
  prompt_version: string;
  input_snapshot?: Record<string, unknown> | null;
  result: AnalysisResult | AnalysisFailure | null;
  demand_level: DemandLevel | null;
  confidence: number | null;
  created_at: string;
};

export type AnalysisSummary = {
  id: string;
  status: AnalysisStatus;
  demand_level: DemandLevel | null;
  confidence: number | null;
  created_at: string;
};

export const DEMAND_LABELS: Record<DemandLevel, string> = {
  strong: "قوي",
  moderate: "متوسط",
  weak: "ضعيف",
  inconclusive: "غير حاسم",
};

export const DEMAND_STYLES: Record<DemandLevel, string> = {
  strong: "bg-green-100 text-green-800",
  moderate: "bg-amber-100 text-amber-800",
  weak: "bg-red-100 text-red-800",
  inconclusive: "bg-zinc-200 text-zinc-700",
};

export const ISSUE_TYPE_LABELS: Record<IssueType, string> = {
  content: "المحتوى",
  channel: "القناة",
  targeting: "الاستهداف",
  budget: "الميزانية",
  audience: "الجمهور",
};

export const ISSUE_TYPE_ORDER: IssueType[] = [
  "content",
  "channel",
  "targeting",
  "budget",
  "audience",
];

export const SEVERITY_LABELS: Record<Severity, string> = {
  low: "منخفضة",
  medium: "متوسطة",
  high: "عالية",
};

export const SEVERITY_STYLES: Record<Severity, string> = {
  low: "bg-zinc-200 text-zinc-700",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-red-100 text-red-800",
};

export const ACTION_LABELS: Record<RecommendationAction, string> = {
  keep: "الإبقاء",
  pause: "الإيقاف",
  increase_budget: "رفع الميزانية",
  decrease_budget: "خفض الميزانية",
  change_copy: "تغيير النص",
  change_creative: "تغيير التصميم",
  change_targeting: "تغيير الاستهداف",
};

export const STATUS_LABELS: Record<AnalysisStatus, string> = {
  succeeded: "مكتمل",
  degraded: "متدهور",
  failed: "فاشل",
};

export function isAnalysisResult(
  result: Analysis["result"],
): result is AnalysisResult {
  return (
    typeof result === "object" &&
    result !== null &&
    "demand" in result &&
    "recommendations" in result
  );
}

export function failureMessage(result: Analysis["result"]): string | null {
  if (result === null || isAnalysisResult(result)) {
    return null;
  }
  return result.degraded_reason ?? result.error ?? null;
}

export function confidencePercent(
  value: number | null | undefined,
): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${Math.round(value * 100)}%`;
}
