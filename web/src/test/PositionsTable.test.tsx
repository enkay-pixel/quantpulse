import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PositionsTable } from "../components/PositionsTable";

describe("PositionsTable", () => {
  it("renders long and short rows with context", () => {
    render(
      <PositionsTable
        positions={{
          date: "2026-07-16",
          model_version: "1",
          rows: [
            { ticker: "NVDA", weight: 0.1, side: "long", latest_close: 190.5, latest_score: 0.03 },
            { ticker: "KO", weight: -0.1, side: "short", latest_close: 82.4, latest_score: -0.01 },
          ],
        }}
      />,
    );
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    expect(screen.getByText("long")).toBeInTheDocument();
    expect(screen.getByText("short")).toBeInTheDocument();
    expect(screen.getByText("$190.50")).toBeInTheDocument();
  });

  it("shows an empty state", () => {
    render(<PositionsTable positions={{ date: null, model_version: null, rows: [] }} />);
    expect(screen.getByText(/No positions yet/)).toBeInTheDocument();
  });
});
