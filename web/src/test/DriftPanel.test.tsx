import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { DriftStatus } from "../api/types";
import { DriftPanel, driftVerdict } from "../components/DriftPanel";

const LIMITS = { psi_threshold: 0.2, share_threshold: 0.3 };

function drift(over: Partial<DriftStatus>): DriftStatus {
  return { date: "2026-07-17", share_drifted: 0, drifted: false, features: [], ...LIMITS, ...over };
}

describe("DriftPanel", () => {
  it("names each input in plain words, keeping its code name small beside it", () => {
    render(
      <DriftPanel
        drift={drift({
          share_drifted: 0.08,
          features: [
            { feature: "ma_ratio_63", psi: 0.19, drifted: false },
            { feature: "vol_21", psi: 0.05, drifted: false },
          ],
        })}
      />,
    );
    const row = screen.getByTestId("drift-ma_ratio_63");
    expect(within(row).getByText(/Price vs its 3-month average/)).toBeInTheDocument();
    expect(within(row).getByText("ma_ratio_63")).toBeInTheDocument();
    expect(screen.getByText(/stable/)).toBeInTheDocument();
  });

  it("marks a drifted input in words, not colour alone", () => {
    render(
      <DriftPanel drift={drift({ features: [{ feature: "ret_5", psi: 0.31, drifted: true }] })} />,
    );
    expect(screen.getByText(/⚠ drifted/)).toBeInTheDocument();
  });

  it("shows the retrain flag when drifted", () => {
    render(<DriftPanel drift={drift({ share_drifted: 0.5, drifted: true })} />);
    expect(screen.getByText(/retrain triggered/)).toBeInTheDocument();
  });

  it("handles missing data", () => {
    render(<DriftPanel drift={drift({ date: null, share_drifted: null, drifted: null })} />);
    expect(screen.getByText(/No drift checks/)).toBeInTheDocument();
  });
});

describe("driftVerdict", () => {
  it("answers the question, and says when an input is close to the line", () => {
    // 0.191 means nothing on its own; against a line at 0.20 it is the one to watch.
    const text = driftVerdict(
      drift({
        features: [
          { feature: "ma_ratio_63", psi: 0.191, drifted: false },
          { feature: "ret_1", psi: 0.03, drifted: false },
        ],
      }),
    );
    expect(text).toMatch(/^No\. None of the model's 2 inputs have moved past the alarm level \(0\.20\)/);
    expect(text).toMatch(/closest is price vs its 3-month average, at 0\.19 — near the line/);
  });

  it("says yes, and why, when the model is being retrained", () => {
    const text = driftVerdict(
      drift({
        drifted: true,
        features: [
          { feature: "ret_5", psi: 0.31, drifted: true },
          { feature: "vol_21", psi: 0.25, drifted: true },
          { feature: "ret_1", psi: 0.02, drifted: false },
        ],
      }),
    );
    expect(text).toMatch(/^Yes\. 2 of the model's 3 inputs have moved past the alarm level/);
  });
});
