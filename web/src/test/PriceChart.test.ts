import { describe, expect, it } from "vitest";

import { priceAxisDigits, signalAxisDigits } from "../components/PriceChart";

describe("priceAxisDigits", () => {
  const pence = { symbol: "£", divisor: 100 };

  it("draws whole pounds for a share worth tens of pounds", () => {
    expect(priceAxisDigits([{ close: 1428 }, { close: 2719 }], pence)).toBe(0);
  });

  it("keeps pence for a share worth about a pound, where whole pounds would repeat", () => {
    // Lloyds at 105p: whole units would label every tick £1.
    expect(priceAxisDigits([{ close: 85 }, { close: 105 }], pence)).toBe(2);
  });

  it("reads the price in the market's units, not as stored", () => {
    expect(priceAxisDigits([{ close: 105 }], { symbol: "$", divisor: 1 })).toBe(0);
  });
});

describe("signalAxisDigits", () => {
  it("keeps a decimal for forecasts of a percent or two, where whole percents would repeat", () => {
    expect(signalAxisDigits([{ score: 0.004 }, { score: -0.018 }])).toBe(1);
  });

  it("drops it once forecasts are large enough to label in whole percents", () => {
    expect(signalAxisDigits([{ score: 0.08 }, { score: -0.02 }])).toBe(0);
  });
});
