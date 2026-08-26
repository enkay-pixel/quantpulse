import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChampionRecordCard } from "../components/ChampionRecordCard";

const WITHDRAWN = {
  model_version: "1",
  n_days: 25,
  start_date: "2026-07-20",
  end_date: "2026-08-21",
  total_return: -0.0203,
  avg_daily_return: -0.0008,
  max_drawdown: -0.032,
  sharpe: -2.15,
  win_rate: 0.44,
  is_current: false,
};
const CURRENT_ONE_DAY = {
  model_version: "9",
  n_days: 1,
  start_date: "2026-08-24",
  end_date: "2026-08-24",
  total_return: 0.0033,
  avg_daily_return: 0.0033,
  max_drawdown: 0,
  sharpe: null,
  win_rate: null,
  is_current: true,
};

describe("ChampionRecordCard", () => {
  it("withholds ratios from a champion with too few sessions", () => {
    // Deliberately fed ratios the mart would have nulled. The card must apply the floor
    // itself: leaning on the mart means any future caller computing its own numbers gets a
    // 100% win rate on a single session rendered as though it meant something.
    const unnulled = { ...CURRENT_ONE_DAY, sharpe: 8.4, win_rate: 1.0 };
    render(<ChampionRecordCard data={{ champions: [WITHDRAWN, unnulled] }} />);
    const rows = screen.getAllByRole("row");
    const v9 = rows.find((r) => r.textContent?.includes("v9"));
    expect(v9?.textContent).toContain("+0.33%"); // return is honest at any size
    expect(v9?.textContent).not.toContain("100.0%"); // win rate is not
    expect(v9?.textContent).not.toContain("8.4"); // nor the Sharpe
  });

  it("still shows the ratios for a champion that has earned them", () => {
    render(
      <ChampionRecordCard data={{ champions: [WITHDRAWN, CURRENT_ONE_DAY] }} />,
    );
    const rows = screen.getAllByRole("row");
    const v1 = rows.find((r) => r.textContent?.includes("v1"));
    expect(v1?.textContent).toContain("-2.15");
    expect(v1?.textContent).toContain("44.0%");
  });

  it("says which model is running and which was withdrawn", () => {
    // The dates alone do not say it: a demotion leaves the outgoing champion's last day
    // adjacent to the incoming one's first.
    render(
      <ChampionRecordCard data={{ champions: [WITHDRAWN, CURRENT_ONE_DAY] }} />,
    );
    expect(screen.getByText("current")).toBeInTheDocument();
    expect(screen.getByText("withdrawn")).toBeInTheDocument();
  });

  it("warns that the headline still belongs to earlier champions", () => {
    // The point of the card. 25 of 26 NYSE live sessions were a model demoted days earlier,
    // so the market's headline figures describe something no longer running.
    render(
      <ChampionRecordCard data={{ champions: [WITHDRAWN, CURRENT_ONE_DAY] }} />,
    );
    expect(
      screen.getByText(/too few to read as performance/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/25 sessions of earlier champions/),
    ).toBeInTheDocument();
  });

  it("shows an empty state before any champion has scored live", () => {
    render(<ChampionRecordCard data={{ champions: [] }} />);
    expect(
      screen.getByText(/Appears once a champion has scored/),
    ).toBeInTheDocument();
  });
});
