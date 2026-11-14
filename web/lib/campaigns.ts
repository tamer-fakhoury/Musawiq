import { formatCurrency, formatDate as formatDateLocale } from "@/lib/i18n";

export type Campaign = {
  id: string;
  name: string;
  provider: string;
  objective: string;
  status: string;
  budget_minor: number;
  currency: string;
  start_at: string;
  end_at: string;
};

export type AdVariation = {
  id: string;
  name: string | null;
  headline: string | null;
  copy_text: string;
  status: string;
};

export type AdSet = {
  id: string;
  name: string;
  status: string;
  variations?: AdVariation[];
};

export type CopyVariant = {
  headline: string;
  copy_text: string;
  description: string;
  angle_ar: string;
};

export type MetricSnapshot = {
  period_start: string;
  period_end: string;
  impressions: number;
  clicks: number;
  spend_minor: number;
  ctr?: number | null;
  cpc_minor?: number | null;
  conversions?: number | null;
};

export type CampaignDetail = Campaign & {
  ad_sets?: AdSet[];
  signals?: MetricSnapshot[];
  product?: { id: string; name: string } | null;
  landing_pages?: {
    id: string;
    slug: string;
    status: string;
    published_url: string | null;
  }[];
  tracking_links?: {
    id: string;
    token: string;
    destination_url: string;
    ad_variation_id: string | null;
    landing_page_id: string | null;
  }[];
};

export const PROVIDERS = [
  { value: "meta", label: "ميتا" },
  { value: "tiktok", label: "تيك توك" },
  { value: "google", label: "جوجل" },
  { value: "snapchat", label: "سناب شات" },
] as const;

const STATUS_LABELS: Record<string, string> = {
  draft: "مسودة",
  submitted: "مُرسلة",
  active: "نشطة",
  paused: "متوقفة",
  rejected: "مرفوضة",
  failed: "فاشلة",
  completed: "مكتملة",
  approved: "معتمدة",
  discarded: "مهملة",
};

export function providerLabel(value: string): string {
  return PROVIDERS.find((provider) => provider.value === value)?.label ?? value;
}

export function statusLabel(value: string): string {
  return STATUS_LABELS[value] ?? value;
}

export function formatMoney(minor: number, currency: string): string {
  return formatCurrency(minor, currency);
}

export function formatDate(value: string): string {
  return formatDateLocale(value);
}

export function variationLabel(variation: AdVariation): string {
  return variation.name ?? variation.headline ?? variation.id.slice(0, 8);
}
