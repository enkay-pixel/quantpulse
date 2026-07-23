import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AlphaBetaCard } from "../components/AlphaBetaCard";

const REPLAY = {
  phase: "replay" as const,
  n_days: 2082,
  beta: -0.047,
  alpha_daily: -0.0000222,
  alpha_annualized: -0.0056,
  r_squared: 0.006,
  correlation: -0.077,
  tracking_error: 0.229,
  information_ratio: -0.569,
};

describe("AlphaBetaCard", () => {
  it("shows the decomposition and calls out market-neutrality", () => {
    render(<AlphaBetaCard data={{ phases: [REPLAY] }} />);
    expect(screen.getByText("-0.05")).toBeInTheDocument(); // beta
    expect(screen.getByText("-0.56%")).toBeInTheDocument(); // annualized alpha
    expect(screen.getByText(/barely moves with the market/)).toBeInTheDocument();
    expect(screen.getByText(/the signal is not paying for itself/)).toBeInTheDocument();
  });

  it("names the disagreement when alpha is positive but the information ratio is not", () => {
    // Regression: the card used to read "it earns positive alpha" while a negative IR sat
    // in the next column — a verdict the numbers had not reached.
    const conflicted = { ...REPLAY, alpha_annualized: 0.0474, information_ratio: -0.34 };
    render(<AlphaBetaCard data={{ phases: [conflicted] }} />);
    expect(screen.getByText(/information ratio is negative/)).toBeInTheDocument();
    expect(screen.getByText(/point opposite ways, so neither one settles it/)).toBeInTheDocument();
  });

  it("says the two agree when they actually agree", () => {
    const good = { ...REPLAY, alpha_annualized: 0.03, information_ratio: 0.4 };
    render(<AlphaBetaCard data={{ phases: [good] }} />);
    expect(screen.getByText(/information ratio agrees/)).toBeInTheDocument();
  });

  it("labels a replay window as a fit, never as skill", () => {
    render(<AlphaBetaCard data={{ phases: [REPLAY] }} />);
    expect(screen.getByText(/not as evidence of skill/)).toBeInTheDocument();
  });

  it("drops the in-sample caveat once the window is genuinely out-of-sample", () => {
    const live = { ...REPLAY, phase: "live" as const, n_days: 40 };
    render(<AlphaBetaCard data={{ phases: [REPLAY, live] }} />);
    expect(screen.getByText(/Live out-of-sample, 40 days/)).toBeInTheDocument();
    expect(screen.queryByText(/not as evidence of skill/)).not.toBeInTheDocument();
  });

  it("falls back to replay while the live phase is too short to regress", () => {
    const live = { ...REPLAY, phase: "live" as const, n_days: 3 };
    render(<AlphaBetaCard data={{ phases: [REPLAY, live] }} />);
    expect(screen.getByText(/In-sample replay, 2082 days/)).toBeInTheDocument();
  });

  it("names the market's own benchmark, not a hardcoded SPY", () => {
    // A JSE book compared to SPY would measure the rand and the S&P, not the strategy.
    render(<AlphaBetaCard data={{ phases: [REPLAY] }} benchmark="STX40.JO" />);
    expect(screen.getByText("Beta vs STX40.JO")).toBeInTheDocument();
    expect(screen.queryByText(/vs SPY/)).not.toBeInTheDocument();
  });

  it("shows an empty state before the marts exist", () => {
    render(<AlphaBetaCard data={{ phases: [] }} />);
    expect(screen.getByText(/Appears after the first dbt transform run/)).toBeInTheDocument();
  });
});
