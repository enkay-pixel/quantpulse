import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FreshnessStrip } from "../components/FreshnessStrip";

describe("FreshnessStrip", () => {
  it("renders all four pipeline stages", () => {
    render(
      <FreshnessStrip
        freshness={{
          latest_price_date: "2026-07-20",
          latest_feature_date: "2026-07-20",
          latest_prediction_date: "2026-07-20",
          latest_snapshot_date: "2026-07-17",
        }}
      />,
    );
    expect(screen.getByText("Prices")).toBeInTheDocument();
    expect(screen.getByText("Features")).toBeInTheDocument();
    expect(screen.getByText("Predictions")).toBeInTheDocument();
    expect(screen.getByText("Portfolio")).toBeInTheDocument();
  });

  it("flags a stage lagging beyond the staleness window", () => {
    render(
      <FreshnessStrip
        freshness={{
          latest_price_date: "2026-07-20",
          latest_feature_date: "2026-07-20",
          latest_prediction_date: "2026-07-20",
          latest_snapshot_date: "2026-07-01", // 19 days behind
        }}
      />,
    );
    expect(screen.getByText(/⚠/)).toBeInTheDocument();
  });

  it("returns nothing when all stages are empty", () => {
    const { container } = render(
      <FreshnessStrip
        freshness={{
          latest_price_date: null,
          latest_feature_date: null,
          latest_prediction_date: null,
          latest_snapshot_date: null,
        }}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
