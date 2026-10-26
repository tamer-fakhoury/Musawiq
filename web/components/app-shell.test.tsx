import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppShell } from "@/components/app-shell";

describe("AppShell", () => {
  it("renders the brand and an Arabic nav item", () => {
    render(
      <AppShell>
        <p>حالة فارغة</p>
      </AppShell>,
    );

    expect(screen.getByText("Musawiq")).toBeInTheDocument();
    expect(screen.getByText("لوحة التحكم")).toBeInTheDocument();
  });
});
