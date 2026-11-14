import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import LoginPage from "@/app/login/page";
import { LanguageProvider } from "@/lib/i18n";

beforeEach(() => {
  window.localStorage.clear();
  document.cookie = "msq_locale=; path=/; max-age=0";
  document.documentElement.lang = "ar";
  document.documentElement.dir = "rtl";
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000";
});

afterEach(() => {
  cleanup();
});

describe("directionality", () => {
  it("defaults to RTL Arabic while keeping email inputs LTR", async () => {
    render(
      <LanguageProvider>
        <LoginPage />
      </LanguageProvider>,
    );

    await waitFor(() => expect(document.documentElement.dir).toBe("rtl"));
    expect(document.documentElement.lang).toBe("ar");
    expect(screen.getByLabelText("البريد الإلكتروني")).toHaveAttribute(
      "dir",
      "ltr",
    );
    expect(screen.getByLabelText("كلمة المرور")).toHaveAttribute("dir", "ltr");
  });

  it("switches the document to LTR English and persists the choice", async () => {
    render(
      <LanguageProvider>
        <LoginPage />
      </LanguageProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "English" }));

    await waitFor(() => expect(document.documentElement.dir).toBe("ltr"));
    expect(document.documentElement.lang).toBe("en");
    expect(window.localStorage.getItem("msq_locale")).toBe("en");
    expect(document.cookie).toContain("msq_locale=en");
    expect(await screen.findByLabelText("Email address")).toHaveAttribute(
      "dir",
      "ltr",
    );
  });
});
