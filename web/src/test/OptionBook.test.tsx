import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { OptionBookCohort, OptionBookOut } from "../api/types";
import { OptionBookCard, optionBookVerdict } from "../components/OptionBookCard";

function cohort(over: Partial<OptionBookCohort>): OptionBookCohort {
  return {
    opened: "2026-08-12",
    exit_date: "2026-09-11",
    phase: "replay",
    spreads: 18,
    skipped: 2,
    options_return: 0.012,
    return_on_premium: 0.12,
    shares_return: 0.008,
    ...over,
  };
}

function book(over: Partial<OptionBookOut>): OptionBookOut {
  return { exchange: "XNYS", live_since: "2026-10-19", risk_budget: 0.1, days: [], cohorts: [], positions: [], ...over };
}

describe("optionBookVerdict", () => {
  it("says what happens next when nothing has opened", () => {
    expect(optionBookVerdict(book({}))).toMatch(/has not opened a cohort yet/);
  });

  it("refuses to compare before any cohort has closed", () => {
    const text = optionBookVerdict(book({ cohorts: [cohort({ exit_date: null })] }));
    expect(text).toMatch(/1 cohort so far — 1 replayed from before .*2026, 0 live/);
    expect(text).toMatch(/None has closed yet/);
  });

  it("compares with the same names as shares, and says how little two months can show", () => {
    const text = optionBookVerdict(
      book({ cohorts: [cohort({}), cohort({ opened: "2026-09-11", exit_date: "2026-10-12", options_return: -0.004, return_on_premium: -0.04, shares_return: 0.002 })] }),
    );
    expect(text).toMatch(/Over the 2 closed, the options book made \+0\.4% a month on its value/);
    expect(text).toMatch(/\+4% on what it paid for its spreads/);
    expect(text).toMatch(/against \+0\.5% for the same names held as shares/);
    expect(text).toMatch(/With 2 months that difference says nothing yet/);
    expect(text).toMatch(/risks 10% of the book/);
  });
});

describe("OptionBookCard", () => {
  it("lists the newest spreads and names what it could not trade, with why", () => {
    render(
      <OptionBookCard
        data={book({
          days: [{ date: "2026-10-12", equity: 1.01, phase: "replay", share_equity: 1.0 }],
          cohorts: [cohort({ opened: "2026-10-12", exit_date: null })],
          positions: [
            { ticker: "AAPL", side: "long", status: "open", note: null, option_type: "call", expiry: "2026-11-20", long_strike: 340, short_strike: 375, entry_debit: 9.8, mark_value: 10.4, mark_basis: "quote", mark_date: "2026-10-16", return_on_premium: 0.06 },
            { ticker: "SPY", side: "long", status: "skipped", note: "no captured expiry reaches the exit", option_type: null, expiry: null, long_strike: null, short_strike: null, entry_debit: null, mark_value: null, mark_basis: null, mark_date: null, return_on_premium: null },
          ],
        })}
      />,
    );
    expect(within(screen.getByTestId("spread-AAPL")).getByText("Bull call 340/375")).toBeInTheDocument();
    expect(screen.getByText(/Could not trade: SPY \(no captured expiry reaches the exit\)/)).toBeInTheDocument();
    expect(screen.queryByTestId("spread-SPY")).not.toBeInTheDocument();
  });
});
