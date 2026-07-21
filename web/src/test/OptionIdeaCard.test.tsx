import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OptionIdeaCard } from "../components/OptionIdeaCard";

const IDEA = {
  ticker: "NVDA",
  available: true,
  signal: 0.031,
  direction: "bullish",
  structure: "bull call spread",
  rationale: "Model's 21-day forecast is +3.1% (bullish); a defined-risk call spread…",
  expiry: "2026-07-31",
  legs: [
    { action: "buy", option_type: "call", strike: 205, price: 6.4 },
    { action: "sell", option_type: "call", strike: 227.5, price: 0.455 },
  ],
  net_debit: 5.95,
  max_profit: 16.55,
  max_loss: 5.95,
  breakeven: 210.95,
};

describe("OptionIdeaCard", () => {
  it("renders the structure, legs, and risk metrics", () => {
    render(<OptionIdeaCard idea={IDEA} />);
    expect(screen.getByText("bull call spread")).toBeInTheDocument();
    expect(screen.getByText("buy")).toBeInTheDocument();
    expect(screen.getByText("sell")).toBeInTheDocument();
    // net debit and max loss are equal for a debit spread, so this appears twice
    expect(screen.getAllByText("$5.95")).toHaveLength(2);
    expect(screen.getByText("$210.95")).toBeInTheDocument(); // breakeven
  });

  it("always shows the not-advice disclaimer", () => {
    render(<OptionIdeaCard idea={IDEA} />);
    expect(screen.getByText(/not advice/)).toBeInTheDocument();
    expect(screen.getByText(/lose 100%/)).toBeInTheDocument();
  });

  it("explains a weak signal and still disclaims", () => {
    render(<OptionIdeaCard idea={{ ...IDEA, available: false, signal: 0.004 }} />);
    expect(screen.getByText(/too weak to express/)).toBeInTheDocument();
    expect(screen.getByText(/not advice/)).toBeInTheDocument();
  });

  it("handles no data at all", () => {
    render(<OptionIdeaCard idea={{ ...IDEA, available: false, signal: null }} />);
    expect(screen.getByText(/No structure available yet/)).toBeInTheDocument();
  });
});
