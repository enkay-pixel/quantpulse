import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { OwnershipRow } from "../api/types";
import { OwnershipDetail } from "../components/OwnershipDetail";
import { OwnershipTable, ownershipVerdict } from "../components/OwnershipTable";

function row(over: Partial<OwnershipRow>): OwnershipRow {
  return {
    ticker: "AAPL",
    followed_by: "model",
    bought_usd_90d: 0,
    sold_usd_90d: 4.2e7,
    buyers_90d: 0,
    sellers_90d: 3,
    planned_sold_share_90d: 0.9,
    last_trade_date: "2026-10-12",
    holders_over_5pct: 2,
    activist_holder: false,
    top_holder: "Vanguard Capital Management",
    top_holder_percent: 7.48,
    ...over,
  };
}

describe("ownershipVerdict", () => {
  it("says no one bought, and that this is common, when insiders only sold", () => {
    const text = ownershipVerdict([row({})]);
    expect(text).toMatch(/^No insider bought on the open market/);
    expect(text).toMatch(/most such selling is routine/);
  });

  it("names the companies where insiders bought, and any activist holder", () => {
    const text = ownershipVerdict([
      row({}),
      row({ ticker: "GME", followed_by: "watchlist", bought_usd_90d: 1e6, buyers_90d: 1, activist_holder: true }),
    ]);
    expect(text).toMatch(/at 1 of these 2 companies in the past 90 days: GME/);
    expect(text).toMatch(/13D filer\) holds over 5% of GME/);
  });
});

describe("OwnershipTable", () => {
  it("reads a filing's percent as a percent, not a fraction, and tags watchlist names", () => {
    render(
      <OwnershipTable
        data={{
          exchange: "XNYS",
          as_of: "2026-10-16",
          rows: [row({}), row({ ticker: "GME", followed_by: "watchlist", top_holder: "Cohen Ryan", top_holder_percent: 9.1 })],
        }}
        selected={null}
        onSelect={vi.fn()}
      />,
    );
    const gme = screen.getByTestId("ownership-GME");
    expect(within(gme).getByText("9.1%")).toBeInTheDocument();
    expect(within(gme).getByText("watchlist")).toBeInTheDocument();
    expect(within(screen.getByTestId("ownership-AAPL")).getByText("7.5%")).toBeInTheDocument();
  });
});

describe("OwnershipDetail", () => {
  it("lists holders and trades, and says so plainly when there are none", () => {
    const { unmount } = render(
      <OwnershipDetail
        data={{
          ticker: "GME",
          holders: [{ filer: "Cohen Ryan", form: "SCHEDULE 13D/A", filed: "2026-10-13", shares_held: 4.6e7, percent: 9.1 }],
          trades: [
            {
              transaction_date: "2026-10-12",
              filed: "2026-10-14",
              owner: "Moore Daniel William",
              role: "PFO and PAO",
              trade: "sold",
              shares_traded: 15480,
              trade_price: 27,
              value_usd: 417960,
              planned: true,
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("13D/A")).toBeInTheDocument();
    expect(screen.getByText("$418K")).toBeInTheDocument();
    unmount();
    render(<OwnershipDetail data={{ ticker: "X", holders: [], trades: [] }} />);
    expect(screen.getByText(/No holder has a current filing/)).toBeInTheDocument();
    expect(screen.getByText(/No open-market insider trade/)).toBeInTheDocument();
  });
});
