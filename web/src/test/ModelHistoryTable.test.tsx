import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ModelHistoryTable } from "../components/ModelHistoryTable";

describe("ModelHistoryTable", () => {
  it("renders promoted and rejected runs with metrics", () => {
    render(
      <ModelHistoryTable
        runs={[
          {
            id: 2,
            run_type: "train",
            model_version: "2",
            decision: "rejected",
            metrics: { holdout_ic: 0.01, holdout_sharpe: 0.4, holdout_max_drawdown: -0.2 },
            mlflow_run_id: "b",
            created_at: "2026-07-19T09:00:00",
          },
          {
            id: 1,
            run_type: "train",
            model_version: "1",
            decision: "promoted",
            metrics: { holdout_ic: 0.026, holdout_sharpe: 0.21, holdout_max_drawdown: -0.05 },
            mlflow_run_id: "a",
            created_at: "2026-07-18T09:00:00",
          },
        ]}
      />,
    );
    expect(screen.getByText("✓ promoted")).toBeInTheDocument();
    expect(screen.getByText("✗ rejected")).toBeInTheDocument();
    expect(screen.getByText("0.026")).toBeInTheDocument();
  });

  it("shows an empty state", () => {
    render(<ModelHistoryTable runs={[]} />);
    expect(screen.getByText(/No training runs/)).toBeInTheDocument();
  });
});
