import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/lib/api";

const originalRole = process.env.NEXT_PUBLIC_DEMO_USER_ROLE;
const originalLegacyRole = process.env.NEXT_PUBLIC_DEMO_ROLE;
const originalBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

afterEach(() => {
  vi.unstubAllGlobals();
  process.env.NEXT_PUBLIC_DEMO_USER_ROLE = originalRole;
  process.env.NEXT_PUBLIC_DEMO_ROLE = originalLegacyRole;
  process.env.NEXT_PUBLIC_API_BASE_URL = originalBaseUrl;
});

describe("apiFetch demo headers", () => {
  it("honors the documented role environment variable", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.test";
    process.env.NEXT_PUBLIC_DEMO_USER_ROLE = "analyst";
    process.env.NEXT_PUBLIC_DEMO_ROLE = "owner";
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/test");

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Headers;
    expect(headers.get("X-User-Role")).toBe("analyst");
  });
});
