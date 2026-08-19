import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TrackRecordCard } from "../components/TrackRecordCard";

const REPLAY = {
  phase: "replay" as const,
  n_days: 823,
  start_date: "2023-04-04",
  end_date: "2026-07-16",
  total_return: 0.8563,
  annualized_volatility: 0.08,
  sharpe: 1.85,
  max_drawdown: -0.0918,
  win_rate: 0.55,
};

describe("TrackRecordCard", () => {
  it("shows accumulating state before any live days", () => {
    render(<TrackRecordCard record={{ live_since: "2026-07-18", phases: [REPLAY] }} />);
    expect(screen.getByText(/Accumulating/)).toBeInTheDocument();
    expect(screen.getByText(/since Jul 18, 2026/)).toBeInTheDocument();
    expect(screen.getByText(/In-sample replay/)).toBeInTheDocument();
    expect(screen.getByText(/not evidence of skill/)).toBeInTheDocument();
  });

  it("explains an empty market rather than implying data is on the way", () => {
    // A market whose first candidate failed the promotion gate has no phases at all.
    // "Accumulating" would wrongly suggest it is merely early.
    render(<TrackRecordCard record={{ live_since: null, phases: [] }} />);
    expect(screen.getByText(/No track record yet for this market/)).toBeInTheDocument();
    expect(screen.getByText(/did not clear the promotion gate/)).toBeInTheDocument();
    expect(screen.queryByText(/Accumulating/)).not.toBeInTheDocument();
  });

  it("claims no start date for a market with no live record", () => {
    // A demoted champion leaves a promotion in the audit trail; the header must not
    // advertise "since <date>" for a track record that never began.
    render(<TrackRecordCard record={{ live_since: "2026-07-23", phases: [] }} />);
    expect(screen.queryByText(/since Jul 23, 2026/)).not.toBeInTheDocument();
  });

  it("shows what the headline cards do not: sample size, window and win rate", () => {
    const live = {
      ...REPLAY,
      phase: "live" as const,
      n_days: 42,
      total_return: 0.031,
      sharpe: 0.9,
      win_rate: 0.52,
    };
    render(<TrackRecordCard record={{ live_since: "2026-07-18", phases: [REPLAY, live] }} />);
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("52%")).toBeInTheDocument();
    expect(screen.queryByText(/Accumulating/)).not.toBeInTheDocument();
  });

  it("does not repeat the headline figures", () => {
    // Return, Sharpe and max drawdown are the LiveStats cards directly above. Showing them
    // again puts the same three numbers twice within a screen of each other.
    const live = {
      ...REPLAY,
      phase: "live" as const,
      n_days: 42,
      total_return: 0.031,
      sharpe: 0.9,
      max_drawdown: -0.0238,
      win_rate: 0.52,
    };
    render(<TrackRecordCard record={{ live_since: "2026-07-18", phases: [REPLAY, live] }} />);
    expect(screen.queryByText("+3.10%")).not.toBeInTheDocument();
    expect(screen.queryByText("0.90")).not.toBeInTheDocument();
    expect(screen.queryByText("-2.38%")).not.toBeInTheDocument();
  });

  it("withholds win rate until the sample can support it", () => {
    // Two days of returns annualize to a confident-looking number that is pure noise.
    const live = {
      ...REPLAY,
      phase: "live" as const,
      n_days: 2,
      total_return: -0.008,
      sharpe: -35.25,
      win_rate: 0,
    };
    render(<TrackRecordCard record={{ live_since: "2026-07-18", phases: [REPLAY, live] }} />);
    expect(screen.getAllByText("—")).toHaveLength(1); // win rate withheld
    expect(screen.getByText(/2 days cannot tell you about a year/)).toBeInTheDocument();
    // Sample size is honest at any size and stays visible.
    expect(screen.getByText("2")).toBeInTheDocument();
  });
});
