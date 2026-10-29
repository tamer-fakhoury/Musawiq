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

  constructor(
    message: string,
    options: { status: number; code: string; correlationId: string },
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.correlationId = options.correlationId;
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
  const role = process.env.NEXT_PUBLIC_DEMO_USER_ROLE || "owner";

  if (storeId) {
    headers.set("X-Store-Id", storeId);
  }
  if (userId) {
    headers.set("X-User-Id", userId);
  }
  headers.set("X-User-Role", role);

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
    ...init,
    headers: demoHeaders(init?.headers),
  });

  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      // Non-JSON error response; fall back to the HTTP status.
    }

    const envelope = isApiErrorBody(body) ? body.error : null;
    throw new ApiError(
      envelope?.message ?? `Request failed with status ${response.status}`,
      {
        status: response.status,
        code: envelope?.code ?? "http_error",
        correlationId: envelope?.correlation_id ?? "",
      },
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
