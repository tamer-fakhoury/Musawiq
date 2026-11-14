import { apiFetch } from "./api";

export type LoginResult = {
  user: {
    id: string;
    email: string;
    full_name: string;
    role: string;
    email_verified_at: string;
  };
  active_store: { id: string; name: string; slug: string; timezone: string } | null;
  csrf_token?: string;
};

export async function login(
  email: string,
  password: string,
): Promise<LoginResult> {
  const result = await apiFetch<LoginResult>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (result.csrf_token && typeof window !== "undefined") {
    window.sessionStorage.setItem("msq_csrf", result.csrf_token);
  }
  return result;
}

export function resendVerification(email: string): Promise<{ sent: boolean }> {
  return apiFetch<{ sent: boolean }>("/auth/verify/resend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
}

export function requestPasswordReset(
  email: string,
): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/auth/password/forgot", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
}

export async function logout(): Promise<void> {
  await apiFetch<void>("/auth/logout", { method: "POST" });
}
