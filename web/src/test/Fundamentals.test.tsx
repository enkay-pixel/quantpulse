import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { FundamentalsRow } from "../api/types";
import { FundamentalsTable, fundamentalsVerdict } from "../components/FundamentalsTable";
import { visibleTabs } from "../lib/tabs";

function row(over: Partial<FundamentalsRow>): FundamentalsRow {
  return {
    ticker: "AAPL",
    followed_by: "model",
    through: "2026-06-27",
    filed: "2026-07-31",
    revenue_ttm: 466.8e9,
    revenue_growth: 0.162,
    revenue_growth_basis: "year to date",
    operating_income_ttm: 155e9,
    net_income_ttm: 129e9,
    free_cash_flow: 136.7e9,
    free_cash_flow_through: "2026-06-27",
    operating_margin: 0.332,
    net_margin: 0.276,
    fcf_margin: 0.293,
    eps_ttm: 8.72,
    cash: 30e9,
    long_term_debt: 85e9,
    debt_to_equity: 0.77,
    market_cap: 5.0e12,
    pe_ratio: 39.4,
    price_to_sales: 10.7,
    fcf_yield: 0.027,
    ...over,
  };
}

describe("fundamentalsVerdict", () => {
  it("counts growers and shrinkers and names the oldest figures", () => {
    const text = fundamentalsVerdict([
      row({}),
      row({ ticker: "KO", revenue_growth: -0.02, through: "2026-04-03" }),
      row({ ticker: "JPM", revenue_growth: 0.028 }),
    ]);
    expect(text).toMatch(/^Of these 3 companies, 1 grew revenue by 10% or more/);
    expect(text).toMatch(/1 sold less: KO\./);
    expect(text).toMatch(/KO's, run through/);
    expect(text).toMatch(/operating margin is the steadier read/);
  });
});

describe("FundamentalsTable", () => {
  it("shows an empty price ratio as a dash, not a zero, and tags watchlist names", () => {
    render(
      <FundamentalsTable
        data={{
          exchange: "XNYS",
          rows: [row({}), row({ ticker: "BRK-B", pe_ratio: null, market_cap: null }), row({ ticker: "GME", followed_by: "watchlist" })],
        }}
      />,
    );
    const brk = screen.getByTestId("fundamentals-BRK-B");
    expect(within(brk).getAllByText("—").length).toBeGreaterThan(0);
    expect(within(screen.getByTestId("fundamentals-AAPL")).getByText("39")).toBeInTheDocument();
    expect(within(screen.getByTestId("fundamentals-GME")).getByText("watchlist")).toBeInTheDocument();
  });
});

describe("the Fundamentals tab", () => {
  it("shows on both markets, the JSE with a plain statement", () => {
    expect(visibleTabs(true)).toContain("Fundamentals");
    expect(visibleTabs(false)).toContain("Fundamentals");
  });
});
