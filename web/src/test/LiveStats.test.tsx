import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LiveStats } from "../components/LiveStats";
import type { PhaseStats } from "../api/types";

const live = (over: Partial<PhaseStats> = {}): PhaseStats => ({
  phase: "live",
  n_days: 21,
  start_date: "2026-07-20",
  end_date: "2026-08-17",
  total_return: -0.0117,
  annualized_volatility: 0.096,
  sharpe: -1.43,
  max_drawdown: -0.0238,
  win_rate: 0.476,
  ...over,
});

describe("LiveStats", () => {
  it("reports the live figures, including when they are negative", () => {
    render(<LiveStats live={live()} />);
    expect(screen.getByText("-1.17%")).toBeInTheDocument();
    expect(screen.getByText("-1.43")).toBeInTheDocument();
    expect(screen.getByText("out-of-sample · 21 sessions")).toBeInTheDocument();
  });

  it("withholds the ratio below the floor but still shows the return", () => {
    render(<LiveStats live={live({ n_days: 12 })} />);
    expect(screen.getByText("withheld under 20 sessions")).toBeInTheDocument();
    expect(screen.queryByText("-1.43")).not.toBeInTheDocument();
    // A total return is honest at any sample size; only the annualized ratio is not.
    expect(screen.getByText("-1.17%")).toBeInTheDocument();
  });

  it("shows nothing rather than falling back to the replay when no live phase exists", () => {
    // The property this row exists for. A replay figure here would read as "this is how it
    // performs" when it only describes a fit, and it is always the flattering number.
    render(<LiveStats live={undefined} />);
    expect(screen.getAllByText("—")).toHaveLength(3);
    expect(screen.getAllByText("no live record yet")).toHaveLength(3);
  });
});
