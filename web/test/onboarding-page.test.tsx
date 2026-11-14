import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OnboardingStorePage from "@/app/onboarding/store/page";

const router = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

function mockFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: async () => body,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
  router.replace.mockReset();
});

beforeEach(() => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000";
});

describe("OnboardingStorePage", () => {
  it("renders the Arabic defaults", () => {
    render(<OnboardingStorePage />);

    expect(screen.getByLabelText("اسم المتجر")).toBeInTheDocument();
    expect(screen.getByLabelText("العملة")).toHaveValue("SAR");
    expect(
      screen.getByLabelText("اللغة", { selector: "input" }),
    ).toHaveValue("ar");
    expect(screen.getByLabelText("المنطقة الزمنية")).toHaveValue(
      "Asia/Riyadh",
    );
    expect(screen.getByLabelText("الدولة")).toHaveValue("SA");
  });

  it("requires a store name and a CSRF token", () => {
    const fetchMock = mockFetch(201, { created: true, store: { id: "s1" } });
    render(<OnboardingStorePage />);

    fireEvent.click(
      screen.getByRole("button", { name: "إنشاء المتجر والمتابعة" }),
    );
    expect(screen.getByText("اسم المتجر مطلوب.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("اسم المتجر"), {
      target: { value: "  Noor Store  " },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "إنشاء المتجر والمتابعة" }),
    );
    expect(
      screen.getByText(
        "انتهت صلاحية الجلسة أو رمز الحماية. يرجى تسجيل الدخول مرة أخرى.",
      ),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("submits trimmed values with the CSRF header and redirects", async () => {
    window.sessionStorage.setItem("msq_csrf", "csrf-value");
    const fetchMock = mockFetch(201, { created: true, store: { id: "s1" } });
    render(<OnboardingStorePage />);

    fireEvent.change(screen.getByLabelText("اسم المتجر"), {
      target: { value: "  Noor Store  " },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "إنشاء المتجر والمتابعة" }),
    );

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-value");
    expect(JSON.parse(init.body)).toEqual({
      name: "Noor Store",
      default_currency: "SAR",
      default_language: "ar",
      timezone: "Asia/Riyadh",
      country_code: "SA",
    });
  });

  it("redirects when the user already has a store", async () => {
    window.sessionStorage.setItem("msq_csrf", "csrf-value");
    mockFetch(200, { created: false, store: { id: "existing" } });
    render(<OnboardingStorePage />);

    fireEvent.change(screen.getByLabelText("اسم المتجر"), {
      target: { value: "Noor Store" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "إنشاء المتجر والمتابعة" }),
    );

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
  });

  it("maps API validation errors inline and prompts re-login on CSRF failure", async () => {
    window.sessionStorage.setItem("msq_csrf", "expired");
    document.cookie = "msq_csrf=expired; path=/";
    mockFetch(403, {
      error: {
        code: "csrf_invalid",
        message: "A valid CSRF token is required.",
        correlation_id: "onboard-c1",
      },
    });
    render(<OnboardingStorePage />);

    fireEvent.change(screen.getByLabelText("اسم المتجر"), {
      target: { value: "Noor Store" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "إنشاء المتجر والمتابعة" }),
    );

    expect(await screen.findByText(/onboard-c1/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "تسجيل الدخول من جديد" }),
    ).toHaveAttribute("href", "/login");
  });
});
