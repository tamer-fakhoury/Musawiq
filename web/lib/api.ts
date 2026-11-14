import { localizeApiError } from "@/lib/error-codes";

export type ApiErrorBody = {
  error: {
    code: string;
    message: string;
    correlation_id: string;
  };
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly correlationId: string;
  readonly retryAfter?: number;

  constructor(
    message: string,
    options: {
      status: number;
      code: string;
      correlationId: string;
      retryAfter?: number;
    },
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.correlationId = options.correlationId;
    this.retryAfter = options.retryAfter;
  }
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const error = (value as { error?: unknown }).error;
  if (typeof error !== "object" || error === null) {
    return false;
  }
  const { code, message, correlation_id } = error as Record<string, unknown>;
  return (
    typeof code === "string" &&
    typeof message === "string" &&
    typeof correlation_id === "string"
  );
}

function demoHeaders(init?: HeadersInit): Headers {
  const headers = new Headers(init);
  const storeId = process.env.NEXT_PUBLIC_DEMO_STORE_ID;
  const userId = process.env.NEXT_PUBLIC_DEMO_USER_ID;
  const role =
    process.env.NEXT_PUBLIC_DEMO_USER_ROLE ||
    process.env.NEXT_PUBLIC_DEMO_ROLE ||
    "owner";

  if (storeId) {
    headers.set("X-Store-Id", storeId);
  }
  if (userId) {
    headers.set("X-User-Id", userId);
  }
  headers.set("X-User-Role", role);

  return headers;
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const AUTH_PAGES = ["/login", "/signup", "/forgot-password"];

function requestHeaders(init?: RequestInit): Headers {
  const headers = demoHeaders(init?.headers);
  const method = (init?.method ?? "GET").toUpperCase();
  if (UNSAFE_METHODS.has(method)) {
    const csrf = readCookie("msq_csrf");
    if (csrf) {
      headers.set("X-CSRF-Token", csrf);
    }
  }
  return headers;
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!baseUrl) {
    throw new ApiError("NEXT_PUBLIC_API_BASE_URL is not configured", {
      status: 0,
      code: "missing_api_base_url",
      correlationId: "",
    });
  }

  const response = await fetch(`${baseUrl}${path}`, {
    credentials: "include",
    ...init,
    headers: requestHeaders(init),
  });

  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      // Non-JSON error response; fall back to the HTTP status.
    }

    const envelope = isApiErrorBody(body) ? body.error : null;
    const retryHeader = response.headers.get("Retry-After");
    const error = new ApiError(
      localizeApiError(envelope?.code ?? "http_error"),
      {
        status: response.status,
        code: envelope?.code ?? "http_error",
        correlationId: envelope?.correlation_id ?? "",
        retryAfter: retryHeader ? Number(retryHeader) : undefined,
      },
    );

    if (
      response.status === 401 &&
      typeof window !== "undefined" &&
      !AUTH_PAGES.includes(window.location.pathname) &&
      !path.startsWith("/auth/")
    ) {
      const next = encodeURIComponent(
        window.location.pathname + window.location.search,
      );
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign(`/login?next=${next}`);
    }
    throw error;
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
