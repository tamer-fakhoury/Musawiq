import { apiFetch } from "./api";

export type LandingPage = {
  id: string;
  product_concept_id: string;
  slug: string;
  status: string;
  language: string;
  direction: "ltr" | "rtl";
  currency: string;
  draft_version: number | null;
  price_minor: number | null;
  content: Record<string, unknown> | null;
  image_file_ids: string[];
  generated_by: string | null;
  model_version: string | null;
  order_method: {
    type: "whatsapp" | "cod";
    whatsapp_number: string | null;
    whatsapp_message_template: string | null;
    cod_form_schema: Record<string, unknown> | null;
    attribution_token: string;
    whatsapp_link: string | null;
  } | null;
};

export type DraftInput = {
  name: string;
  description: string;
  price_minor: number;
  currency: string;
  language: string;
  target_market: string;
  image_file_ids: string[];
  order_method: {
    type: "whatsapp" | "cod";
    whatsapp_number?: string;
  };
};

export function createDraft(
  conceptId: string,
  input: DraftInput,
): Promise<LandingPage> {
  return apiFetch<LandingPage>("/landing-pages/drafts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_concept_id: conceptId, ...input }),
  });
}

export function getPage(id: string): Promise<LandingPage> {
  return apiFetch<LandingPage>(`/landing-pages/${id}`);
}

export function uploadImage(file: File): Promise<{ id: string }> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<{ id: string }>("/landing-pages/images", {
    method: "POST",
    body: form,
  });
}

export function generateCopy(
  id: string,
  force = false,
): Promise<{ headline: string; description: string; cta_label: string }> {
  return apiFetch<{ headline: string; description: string; cta_label: string }>(
    `/landing-pages/${id}/copy`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force }),
    },
  );
}

export function configureChannel(
  id: string,
  body: Record<string, unknown>,
): Promise<LandingPage["order_method"]> {
  return apiFetch<LandingPage["order_method"]>(
    `/landing-pages/${id}/order-channel`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export function verifyChannel(
  id: string,
): Promise<{ valid: boolean; errors: string[] }> {
  return apiFetch<{ valid: boolean; errors: string[] }>(
    `/landing-pages/${id}/order-channel/verify`,
    { method: "POST" },
  );
}

export function generatePage(id: string): Promise<{ job_id: string }> {
  return apiFetch<{ job_id: string }>(`/landing-pages/${id}/generate`, {
    method: "POST",
  });
}
