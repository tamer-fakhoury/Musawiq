import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LoginPage from "@/app/login/page";

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

function fillAndSubmit(email = "merchant@example.com", password = "wrong-pass") {
  fireEvent.change(screen.getByLabelText("البريد الإلكتروني"), {
    target: { value: email },
  });
  fireEvent.change(screen.getByLabelText("كلمة المرور"), {
    target: { value: password },
  });
  fireEvent.click(screen.getByRole("button", { name: "تسجيل الدخول" }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("LoginPage", () => {
  it("renders Arabic fields and the account links", () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000";
    render(<LoginPage />);

    expect(screen.getByLabelText("البريد الإلكتروني")).toBeInTheDocument();
    expect(screen.getByLabelText("كلمة المرور")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "نسيت كلمة المرور؟" }),
    ).toHaveAttribute("href", "/forgot-password");
    expect(
      screen.getByRole("link", { name: "إنشاء حساب" }),
    ).toHaveAttribute("href", "/signup");
  });

  it("shows a generic message for invalid credentials", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000";
    const fetchMock = mockFetch(401, {
      error: {
        code: "invalid_credentials",
        message: "Invalid email or password.",
        correlation_id: "c1",
      },
    });
    render(<LoginPage />);

    fillAndSubmit();

    await waitFor(() =>
      expect(
        screen.getByText("البريد الإلكتروني أو كلمة المرور غير صحيحة."),
      ).toBeInTheDocument(),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/auth/login",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows the unverified message with a resend action", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000";
    mockFetch(403, {
      error: {
        code: "email_unverified",
        message: "Verify your email before signing in.",
        correlation_id: "c2",
      },
    });
    render(<LoginPage />);

    fillAndSubmit();

    expect(
      await screen.findByRole("button", {
        name: "إعادة إرسال رسالة التحقق",
      }),
    ).toBeInTheDocument();
  });

  it("switches login labels to English", async () => {
    const { LanguageProvider } = await import("@/lib/i18n");
    render(
      <LanguageProvider>
        <LoginPage />
      </LanguageProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "English" }));

    expect(screen.getByLabelText("Email address")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log in" })).toBeInTheDocument();
  });
});
