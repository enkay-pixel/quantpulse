import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { IvSurfaceChart } from "../components/IvSurfaceChart";

const term = [
  { days_to_expiry: 7, expiry: "2026-09-04", avg_iv: 0.227, n_contracts: 26 },
  { days_to_expiry: 21, expiry: "2026-09-18", avg_iv: 0.242, n_contracts: 24 },
  { days_to_expiry: 49, expiry: "2026-10-16", avg_iv: 0.249, n_contracts: 22 },
];
const history = [
  { snapshot_date: "2026-07-20", avg_iv: 0.37 },
  { snapshot_date: "2026-08-28", avg_iv: 0.245 },
];
const base = {
  ticker: "AAPL",
  snapshot_date: "2026-08-28",
  term_structure: term,
  history,
};

describe("IvSurfaceChart", () => {
  it("names the shape of the curve rather than leaving it to be eyeballed", () => {
    render(<IvSurfaceChart data={base} />);
    expect(
      screen.getByText(/upward — longer-dated options cost more/),
    ).toBeInTheDocument();
  });

  it("calls an inverted curve inverted, and says what it usually means", () => {
    // Backwardation is the case worth naming: near-dated IV above far-dated usually means a
    // known event before the near expiry, which is a different thing from a rich vol market.
    const inverted = {
      ...base,
      term_structure: [
        { ...term[0], avg_iv: 0.35 },
        { ...term[1], avg_iv: 0.28 },
        { ...term[2], avg_iv: 0.24 },
      ],
    };
    render(<IvSurfaceChart data={inverted} />);
    expect(
      screen.getByText(/inverted — near-dated options cost more/),
    ).toBeInTheDocument();
  });

  it("does not claim a shape from a difference too small to be one", () => {
    const flat = {
      ...base,
      term_structure: term.map((t) => ({ ...t, avg_iv: 0.24 })),
    };
    render(<IvSurfaceChart data={flat} />);
    expect(
      screen.getByText(/flat — no meaningful difference/),
    ).toBeInTheDocument();
  });

  it("says how many snapshots the history rests on", () => {
    // The history is only as long as capture has run; no vendor sells it retroactively, so
    // the count is the reader's guide to how much the line can carry.
    render(<IvSurfaceChart data={base} />);
    expect(screen.getByText(/2 snapshots/)).toBeInTheDocument();
  });

  it("shows an empty state before any snapshot exists", () => {
    render(
      <IvSurfaceChart data={{ ...base, term_structure: [], history: [] }} />,
    );
    expect(
      screen.getByText(/No option snapshots for this ticker yet/),
    ).toBeInTheDocument();
  });
});
