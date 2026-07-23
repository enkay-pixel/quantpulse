import { describe, expect, it } from "vitest";

import { USD, formatMoney } from "../lib/format";

const ZAR = { symbol: "R", divisor: 100 };

describe("formatMoney", () => {
  it("shows US prices unchanged", () => {
    expect(formatMoney(325.89, USD)).toBe("$325.89");
  });

  it("converts JSE cents to rand", () => {
    // Yahoo quotes NPN.JO at 79787 ZAc. Showing that raw overstates it 100x.
    expect(formatMoney(79787, ZAR)).toBe("R797.87");
  });

  it("defaults to USD so existing call sites are unaffected", () => {
    expect(formatMoney(10)).toBe("$10.00");
  });

  it("renders missing values as a dash rather than NaN", () => {
    expect(formatMoney(null, ZAR)).toBe("—");
    expect(formatMoney(undefined)).toBe("—");
    expect(formatMoney(Number.NaN)).toBe("—");
  });
});
