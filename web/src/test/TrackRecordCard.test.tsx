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

  it("shows live stats once the live phase exists", () => {
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
    expect(screen.getByText("+3.10%")).toBeInTheDocument();
    expect(screen.getByText("0.90")).toBeInTheDocument(); // Sharpe shown once there is a sample
    expect(screen.queryByText(/Accumulating/)).not.toBeInTheDocument();
  });

  it("withholds Sharpe and win rate until the sample can support them", () => {
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
    expect(screen.queryByText("-35.25")).not.toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBe(2); // Sharpe and win rate both withheld
    expect(screen.getByText(/2 days cannot tell you about a year/)).toBeInTheDocument();
    expect(screen.getByText("-0.80%")).toBeInTheDocument(); // return still shown
  });
});
