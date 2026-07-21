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
    expect(screen.getByText(/Market-neutral as designed/)).toBeInTheDocument();
    expect(screen.getByText(/earns no positive alpha/)).toBeInTheDocument();
  });

  it("prefers the live phase once it has enough days", () => {
    const live = { ...REPLAY, phase: "live" as const, n_days: 40, alpha_annualized: 0.03 };
    render(<AlphaBetaCard data={{ phases: [REPLAY, live] }} />);
    expect(screen.getByText(/Live out-of-sample, 40 days/)).toBeInTheDocument();
    expect(screen.getByText(/earns positive alpha/)).toBeInTheDocument();
  });

  it("falls back to replay while the live phase is too short to regress", () => {
    const live = { ...REPLAY, phase: "live" as const, n_days: 3 };
    render(<AlphaBetaCard data={{ phases: [REPLAY, live] }} />);
    expect(screen.getByText(/In-sample replay, 2082 days/)).toBeInTheDocument();
  });

  it("shows an empty state before the marts exist", () => {
    render(<AlphaBetaCard data={{ phases: [] }} />);
    expect(screen.getByText(/Appears after the first dbt transform run/)).toBeInTheDocument();
  });
});
