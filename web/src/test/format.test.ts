import { describe, expect, it } from "vitest";

import {
  deltaColor,
  formatDate,
  formatNumber,
  formatPercent,
  formatSignedPercent,
} from "../lib/format";

describe("formatters", () => {
  it("formats percentages", () => {
    expect(formatPercent(0.1234)).toBe("12.34%");
    expect(formatPercent(null)).toBe("—");
    expect(formatPercent(Number.NaN)).toBe("—");
  });

  it("signs percentages only when positive", () => {
    expect(formatSignedPercent(0.05)).toBe("+5.00%");
    expect(formatSignedPercent(-0.05)).toBe("-5.00%");
  });

  it("formats numbers with fallback", () => {
    expect(formatNumber(1.234, 1)).toBe("1.2");
    expect(formatNumber(undefined)).toBe("—");
  });

  it("formats ISO dates", () => {
    expect(formatDate("2026-07-17")).toMatch(/2026/);
    expect(formatDate(null)).toBe("—");
  });

  it("maps delta sign to color tokens", () => {
    expect(deltaColor(0.1)).toBe("var(--delta-up)");
    expect(deltaColor(-0.1)).toBe("var(--delta-down)");
    expect(deltaColor(0)).toBe("var(--text-primary)");
  });
});
