import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PositioningRow } from "../api/types";
import { GammaProfileChart } from "../components/GammaProfileChart";
import {
  PositioningTable,
  gammaVerdict,
  shortBand,
  shortInterestVerdict,
} from "../components/PositioningTable";
import { WatchlistCard } from "../components/WatchlistCard";

function row(over: Partial<PositioningRow>): PositioningRow {
  return {
    ticker: "AAPL",
    asset_type: "stock",
    followed_by: "model",
    spot: 100,
    call_oi: 1000,
    put_oi: 800,
    call_gamma_usd_1pct: 2.2e9,
    put_gamma_usd_1pct: 8e8,
    call_gamma_near_share: 0.88,
    adv_usd_20d: 1.27e10,
    call_gamma_share_of_adv: 0.17,
    put_gamma_share_of_adv: 0.06,
    short_settlement_date: "2026-09-30",
    short_known_from: "2026-10-16",
    shares_short: 120_000_000,
    short_pct_float: 0.008,
    days_to_cover: 2.8,
    short_change: -0.14,
    ...over,
  };
}

describe("shortBand", () => {
  it("names only the commonly cited bands, and nothing below them", () => {
    expect(shortBand(0.25)).toBe("high");
    expect(shortBand(0.12)).toBe("elevated");
    expect(shortBand(0.05)).toBeNull();
    expect(shortBand(null)).toBeNull();
  });
});

describe("shortInterestVerdict", () => {
  it("says the fuel is ordinary when no stock reaches the high band, with GameStop for scale", () => {
    const text = shortInterestVerdict([row({}), row({ ticker: "CRM", short_pct_float: 0.046 })]);
    expect(text).toMatch(/most-shorted of these 2 stocks is CRM, at 4.6%/);
    expect(text).toMatch(/more than 100% at GameStop/);
    expect(text).toMatch(/ordinary/);
  });

  it("names every stock in the high band and calls it fuel, not a forecast", () => {
    const text = shortInterestVerdict([
      row({ ticker: "GME", short_pct_float: 0.31, days_to_cover: 6.2 }),
      row({ ticker: "XYZ", short_pct_float: 0.22 }),
      row({}),
    ]);
    expect(text).toMatch(/^2 of these 3 stocks have 20% or more/);
    expect(text).toMatch(/GME, XYZ/);
    expect(text).toMatch(/not a sign that one is coming/);
  });

  it("leaves ETFs out: their short interest does not mean the same thing", () => {
    const text = shortInterestVerdict([row({}), row({ ticker: "SPY", asset_type: "etf", short_pct_float: 0.9 })]);
    expect(text).not.toMatch(/SPY/);
  });

  it("says when there is nothing yet rather than reporting zero", () => {
    expect(shortInterestVerdict([row({ short_pct_float: null })])).toMatch(/not been fetched yet/);
  });
});

describe("gammaVerdict", () => {
  it("states the largest exposure with the assumption it rests on", () => {
    const text = gammaVerdict([row({}), row({ ticker: "COST", call_gamma_share_of_adv: 0.19, call_gamma_usd_1pct: 4.1e8 })]);
    expect(text).toMatch(/every listed call on COST/);
    expect(text).toMatch(/\$410M/);
    expect(text).toMatch(/19% of a normal day/);
    expect(text).toMatch(/upper bound/);
  });
});

describe("PositioningTable", () => {
  it("ranks stocks by call exposure and lists ETFs apart, below them", () => {
    render(
      <PositioningTable
        data={{
          exchange: "XNYS",
          snapshot_date: "2026-10-15",
          rows: [
            row({ ticker: "SPY", asset_type: "etf", call_gamma_share_of_adv: 0.35 }),
            row({ ticker: "MSFT", call_gamma_share_of_adv: 0.16 }),
            row({ ticker: "COST", call_gamma_share_of_adv: 0.19 }),
          ],
        }}
        selected="COST"
        onSelect={vi.fn()}
      />,
    );
    const order = screen.getAllByTestId(/^positioning-/).map((el) => el.dataset.testid);
    expect(order).toEqual(["positioning-COST", "positioning-MSFT", "positioning-SPY"]);
    expect(screen.getByText(/ETFs, listed apart/)).toBeInTheDocument();
    expect(within(screen.getByTestId("positioning-COST")).getByText(/▸/)).toBeInTheDocument();
  });

  it("explains an empty snapshot instead of drawing an empty table", () => {
    render(
      <PositioningTable data={{ exchange: "XNYS", snapshot_date: null, rows: [] }} selected={null} onSelect={vi.fn()} />,
    );
    expect(screen.getByText(/No positioning yet/)).toBeInTheDocument();
  });
});

describe("GammaProfileChart", () => {
  it("says so when a ticker has no live contracts", () => {
    render(<GammaProfileChart data={{ ticker: "AAPL", snapshot_date: "2026-10-15", spot: 100, strikes: [] }} />);
    expect(screen.getByText(/No live contracts/)).toBeInTheDocument();
  });

  it("labels which side of the axis is which, so colour is never the only key", () => {
    render(
      <GammaProfileChart
        data={{
          ticker: "AAPL",
          snapshot_date: "2026-10-15",
          spot: 100,
          strikes: [{ strike: 100, call_oi: 10, put_oi: 5, call_gamma_usd_1pct: 5e5, put_gamma_usd_1pct: 2e5 }],
        }}
      />,
    );
    expect(screen.getByText("Calls, above the axis")).toBeInTheDocument();
    expect(screen.getByText("Puts, below the axis")).toBeInTheDocument();
  });
});

describe("the research watchlist", () => {
  it("tags a watchlist name in the positioning table and leaves the model's names untagged", () => {
    render(
      <PositioningTable
        data={{
          exchange: "XNYS",
          snapshot_date: "2026-10-16",
          rows: [row({}), row({ ticker: "GME", followed_by: "watchlist" })],
        }}
        selected={null}
        onSelect={vi.fn()}
      />,
    );
    expect(within(screen.getByTestId("positioning-GME")).getByText("watchlist")).toBeInTheDocument();
    expect(within(screen.getByTestId("positioning-AAPL")).queryByText("watchlist")).toBeNull();
  });

  it("lists each name with why it is followed, and says how to add one when empty", () => {
    const { unmount } = render(
      <WatchlistCard
        names={[
          { ticker: "GME", exchange: "XNYS", asset_type: "stock", why: "The 2021 squeeze.", wikipedia: "GameStop" },
        ]}
      />,
    );
    expect(within(screen.getByTestId("watch-GME")).getByText("The 2021 squeeze.")).toBeInTheDocument();
    unmount();
    render(<WatchlistCard names={[]} />);
    expect(screen.getByText(/configs\/watchlist\.yaml/)).toBeInTheDocument();
  });
});
