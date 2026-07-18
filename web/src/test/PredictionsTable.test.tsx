import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PredictionsTable } from "../components/PredictionsTable";

const PREDICTIONS = {
  date: "2026-07-17",
  model_version: "1",
  rows: [
    { ticker: "NVDA", score: 0.042, rank: 1 },
    { ticker: "KO", score: -0.013, rank: 2 },
  ],
};

describe("PredictionsTable", () => {
  it("renders ranked rows with signed scores", () => {
    render(
      <PredictionsTable predictions={PREDICTIONS} selectedTicker={null} onSelect={() => {}} />,
    );
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    expect(screen.getByText("+4.20%")).toBeInTheDocument();
    expect(screen.getByText("-1.30%")).toBeInTheDocument();
  });

  it("invokes onSelect when a row is clicked", () => {
    const onSelect = vi.fn();
    render(<PredictionsTable predictions={PREDICTIONS} selectedTicker={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByText("KO"));
    expect(onSelect).toHaveBeenCalledWith("KO");
  });

  it("shows an empty state without rows", () => {
    render(
      <PredictionsTable
        predictions={{ date: null, model_version: null, rows: [] }}
        selectedTicker={null}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText(/No predictions yet/)).toBeInTheDocument();
  });
});
