import { describe, expect, it } from "vitest";

import { USD, formatMoney, moneyOf } from "../lib/format";

const ZAR = { symbol: "R", divisor: 100 };
const GBP = { symbol: "£", divisor: 100 };

describe("formatMoney", () => {
  it("shows US prices unchanged", () => {
    expect(formatMoney(325.89, USD)).toBe("$325.89");
  });

  it("converts JSE cents to rand", () => {
    // Yahoo quotes NPN.JO at 79787 ZAc. Showing that raw overstates it 100x.
    expect(formatMoney(79787, ZAR)).toBe("R797.87");
  });

  it("converts London pence to pounds", () => {
    expect(formatMoney(1428, GBP)).toBe("£14.28");
  });

  it("shows a dash, not dollars, until the market's convention is known", () => {
    // A default of dollars is how rand and pound prices came to be drawn as dollars.
    expect(formatMoney(1428, undefined)).toBe("—");
  });

  it("reads a market's convention from its registry entry", () => {
    expect(moneyOf({ display_symbol: "£", display_divisor: 100 })).toEqual(GBP);
    expect(moneyOf(undefined)).toBeUndefined();
  });

  it("renders missing values as a dash rather than NaN", () => {
    expect(formatMoney(null, ZAR)).toBe("—");
    expect(formatMoney(undefined, USD)).toBe("—");
    expect(formatMoney(Number.NaN, USD)).toBe("—");
  });
});
