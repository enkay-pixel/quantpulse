import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BookComparisonCard } from "../components/BookComparisonCard";
import type { BookStats } from "../api/types";

// The real measured numbers, so the verdict wording is exercised against live shapes.
const DAILY: BookStats = {
  variant: "daily",
  rebalance_days: 1,
  n_days: 2085,
  total_return: 0.856,
  annualized_return: 0.0776,
  annualized_gross_return: 0.1476,
  sharpe: 0.727,
  max_drawdown: -0.2693,
  mean_turnover: 0.2298,
  annualized_cost_drag: 0.0579,
};

const HORIZON: BookStats = {
  variant: "horizon",
  rebalance_days: 21,
  n_days: 2085,
  total_return: 2.045,
  annualized_return: 0.144,
  annualized_gross_return: 0.1572,
  sharpe: 1.308,
  max_drawdown: -0.1623,
  mean_turnover: 0.0257,
  annualized_cost_drag: 0.0065,
};

describe("BookComparisonCard", () => {
  it("shows both books with their rebalance cadence", () => {
    render(<BookComparisonCard data={{ books: [DAILY, HORIZON] }} />);
    expect(screen.getByText("Daily")).toBeInTheDocument();
    expect(screen.getByText("21-day")).toBeInTheDocument();
    expect(screen.getByText("every 1d")).toBeInTheDocument();
    expect(screen.getByText("every 21d")).toBeInTheDocument();
    expect(screen.getByText("14.40%")).toBeInTheDocument();
    expect(screen.getByText("1.31")).toBeInTheDocument();
  });

  it("attributes the gap mostly to cost, not stock picking", () => {
    render(<BookComparisonCard data={{ books: [DAILY, HORIZON] }} />);
    // 6.64pp net gap, only 0.96pp of it survives before costs, so ~86% is friction
    // (the docs quote 85% off unrounded inputs; these fixtures are rounded).
    expect(screen.getByText(/about 86% of that gap is trading cost/)).toBeInTheDocument();
    expect(screen.getByText(/in-sample/)).toBeInTheDocument();
  });

  it("states the premise that makes the comparison valid", () => {
    render(<BookComparisonCard data={{ books: [DAILY, HORIZON] }} />);
    expect(screen.getByText(/differ only in how often they/)).toBeInTheDocument();
  });

  it("does not claim a cost story when the slower book is not ahead", () => {
    const flipped = { ...HORIZON, annualized_return: 0.01 };
    render(<BookComparisonCard data={{ books: [DAILY, flipped] }} />);
    expect(screen.queryByText(/of that gap is trading cost/)).not.toBeInTheDocument();
    expect(screen.getByText(/not currently behind the slower book/)).toBeInTheDocument();
  });

  it("renders a placeholder before any book exists", () => {
    render(<BookComparisonCard data={{ books: [] }} />);
    expect(screen.getByText(/Appears once the paper books/)).toBeInTheDocument();
  });
});
