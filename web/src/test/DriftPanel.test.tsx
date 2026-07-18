import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DriftPanel } from "../components/DriftPanel";

describe("DriftPanel", () => {
  it("shows stable state and feature bars", () => {
    render(
      <DriftPanel
        drift={{
          date: "2026-07-17",
          share_drifted: 0.08,
          drifted: false,
          features: [
            { feature: "ret_5", psi: 0.31, drifted: true },
            { feature: "vol_21", psi: 0.05, drifted: false },
          ],
        }}
      />,
    );
    expect(screen.getByText(/stable/)).toBeInTheDocument();
    expect(screen.getByText("ret_5")).toBeInTheDocument();
    expect(screen.getByText(/⚠ drifted/)).toBeInTheDocument();
  });

  it("shows retrain flag when drifted", () => {
    render(
      <DriftPanel
        drift={{ date: "2026-07-17", share_drifted: 0.5, drifted: true, features: [] }}
      />,
    );
    expect(screen.getByText(/retrain triggered/)).toBeInTheDocument();
  });

  it("handles missing data", () => {
    render(<DriftPanel drift={{ date: null, share_drifted: null, drifted: null, features: [] }} />);
    expect(screen.getByText(/No drift checks/)).toBeInTheDocument();
  });
});
