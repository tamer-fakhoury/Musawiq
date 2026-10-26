import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppShell } from "@/components/app-shell";

describe("AppShell", () => {
  it("renders the brand and a nav item", () => {
    render(
      <AppShell>
        <p>Empty state</p>
      </AppShell>,
    );

    expect(screen.getByText("Musawiq")).toBeInTheDocument();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
  });
});
