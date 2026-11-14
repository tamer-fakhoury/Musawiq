import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AppShell } from "@/components/app-shell";
import { LanguageProvider } from "@/lib/i18n";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe("AppShell", () => {
  it("renders Arabic navigation by default", () => {
    render(
      <LanguageProvider>
        <AppShell>
          <p>محتوى</p>
        </AppShell>
      </LanguageProvider>,
    );

    expect(screen.getByText("Musawiq")).toBeInTheDocument();
    expect(screen.getByText("لوحة التحكم")).toBeInTheDocument();
  });

  it("switches navigation to English without a reload", () => {
    render(
      <LanguageProvider>
        <AppShell>
          <p>content</p>
        </AppShell>
      </LanguageProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "English" }));

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
  });
});
