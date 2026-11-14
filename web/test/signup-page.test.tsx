import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SignupPage from "@/app/signup/page";

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

function fill(email: string, password: string, confirmation = password) {
  fireEvent.change(screen.getByLabelText("البريد الإلكتروني"), {
    target: { value: email },
  });
  fireEvent.change(screen.getByLabelText("كلمة المرور"), {
    target: { value: password },
  });
  fireEvent.change(screen.getByLabelText("تأكيد كلمة المرور"), {
    target: { value: confirmation },
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

describe("SignupPage", () => {
  it("renders accessible Arabic fields", () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000";
    render(<SignupPage />);

    expect(screen.getByLabelText("البريد الإلكتروني")).toHaveAttribute(
      "autocomplete",
      "email",
    );
    expect(screen.getByLabelText("كلمة المرور")).toHaveAttribute(
      "autocomplete",
      "new-password",
    );
    expect(screen.getByLabelText("تأكيد كلمة المرور")).toHaveAttribute(
      "autocomplete",
      "new-password",
    );
  });

  it("shows inline validation errors before calling the API", () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000";
    const fetchMock = mockFetch(201, { status: "pending_verification" });
    render(<SignupPage />);

    fill("not-an-email", "short", "different");
    fireEvent.click(screen.getByRole("button", { name: "إنشاء الحساب" }));

    expect(screen.getByText("أدخل بريدًا إلكترونيًا صالحًا.")).toBeInTheDocument();
    expect(
      screen.getByText("يجب أن تكون كلمة المرور 12 حرفًا على الأقل."),
    ).toBeInTheDocument();
    expect(screen.getByText("كلمتا المرور غير متطابقتين.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("submits valid credentials and shows the verification state", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000";
    const fetchMock = mockFetch(201, { status: "pending_verification" });
    render(<SignupPage />);

    fill("merchant@example.com", "correct horse battery");
    fireEvent.click(screen.getByRole("button", { name: "إنشاء الحساب" }));

    await waitFor(() =>
      expect(screen.getByText("تحقق من بريدك الإلكتروني")).toBeInTheDocument(),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/auth/signup",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          email: "merchant@example.com",
          password: "correct horse battery",
        }),
      }),
    );
    expect(
      screen.getByRole("link", { name: "الانتقال إلى تسجيل الدخول" }),
    ).toHaveAttribute("href", "/login");
  });

  it("shows the generic duplicate-email error", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000";
    mockFetch(409, {
      error: {
        code: "signup_failed",
        message: "Unable to create an account with these details.",
        correlation_id: "signup-c1",
      },
    });
    render(<SignupPage />);

    fill("merchant@example.com", "correct horse battery");
    fireEvent.click(screen.getByRole("button", { name: "إنشاء الحساب" }));

    expect(
      await screen.findByText("تعذر إنشاء حساب بهذه البيانات."),
    ).toBeInTheDocument();
    expect(screen.getByText("Correlation ID: signup-c1")).toBeInTheDocument();
  });
});
