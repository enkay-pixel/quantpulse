import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BenchmarkEquityChart } from "../components/BenchmarkEquityChart";

const curve = {
  points: [
    { date: "2026-07-20", equity: 1, daily_return: 0, turnover: 0, phase: "live" as const, benchmark_equity: 1, horizon_equity: null },
  ],
  total_return: 0,
  max_drawdown: 0,
  sharpe: null,
};

describe("BenchmarkEquityChart", () => {
  it("names the market's own index fund, never a hardcoded SPY", () => {
    render(<BenchmarkEquityChart curve={curve} benchmark="STX40.JO" />);
    expect(screen.getByText("Index fund (STX40.JO), bought and held")).toBeInTheDocument();
    expect(screen.queryByText(/SPY/)).not.toBeInTheDocument();
  });

  it("says a market without a model has no book yet, not that the pipeline has yet to run", () => {
    render(<BenchmarkEquityChart curve={{ ...curve, points: [] }} />);
    expect(screen.getByText(/once a model clears the promotion gate/)).toBeInTheDocument();
  });
});
