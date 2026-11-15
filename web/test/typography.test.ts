import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf8");

describe("accessibility typography baseline", () => {
  it("uses an 18px base body with 1.6 line height and medium/ bold weights", () => {
    expect(css).toContain("font-size: 112.5%");
    expect(css).toContain("font-size: 1.125rem");
    expect(css).toContain("font-weight: 500");
    expect(css).toContain("line-height: 1.6");
    expect(css).toMatch(/h1,[\s\S]*font-weight: 700/);
  });

  it("keeps helper text at 14px or more", () => {
    expect(css).toContain("--text-xs: 0.875rem");
  });

  it("provides visible focus and 44px tap targets", () => {
    expect(css).toContain("outline: 3px solid #18181b !important");
    expect(css).toContain("min-height: 44px");
    expect(css).toMatch(/button,\s*\[role="button"\]\s*{\s*min-width: 44px/);
  });

  it("gives Arabic longer line height for diacritics", () => {
    expect(css).toMatch(/html\[lang="ar"\] h1/);
    expect(css).toContain("line-height: 1.7");
  });
});
