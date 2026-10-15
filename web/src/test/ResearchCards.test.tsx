import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Decision } from "../api/types";
import { DecisionsCard } from "../components/DecisionsCard";
import { FindingsList } from "../components/FindingsList";
import { ForwardVrpChart } from "../components/ForwardVrpChart";

const standing: Decision = {
  id: "keep-jse-model",
  title: "Keep running the JSE model",
  decided: "2026-08-24",
  note: null,
  state: "standing",
  conditions: [{ type: "live_sessions_at_least", state: "armed", detail: "XJSE live sessions 57 of 60" }],
};

describe("DecisionsCard", () => {
  it("says none has reopened when every condition is armed", () => {
    render(<DecisionsCard data={{ decisions: [standing] }} />);
    expect(screen.getByText(/1 standing decisions, none reopened/)).toBeInTheDocument();
    expect(screen.getByText("standing")).toBeInTheDocument();
    expect(screen.getByText(/57 of 60/)).toBeInTheDocument();
  });

  it("puts a reopened decision in the summary and marks the condition that fired", () => {
    // The page exists to make this moment visible; a reopened decision that read like the
    // others would be the failure.
    const reopened: Decision = {
      ...standing,
      id: "jse-momentum-check-stays",
      title: "Leave the JSE momentum check in the gate",
      state: "reopened",
      conditions: [{ type: "promotion_after", state: "fired", detail: "XJSE promoted a candidate on 2026-10-17" }],
    };
    render(<DecisionsCard data={{ decisions: [standing, reopened] }} />);
    expect(screen.getByText(/1 of 2 standing decisions has reopened/)).toBeInTheDocument();
    const row = screen.getByTestId("decision-jse-momentum-check-stays");
    expect(within(row).getByText("reopened")).toBeInTheDocument();
    expect(within(row).getByText(/▲ XJSE promoted/)).toBeInTheDocument();
  });

  it("does not claim a decision is standing when its condition cannot be checked", () => {
    const unseen: Decision = { ...standing, id: "shadow", state: "unknown" };
    render(<DecisionsCard data={{ decisions: [unseen] }} />);
    expect(screen.getByText("can't check here")).toBeInTheDocument();
    expect(screen.queryByText("standing")).not.toBeInTheDocument();
  });
});

describe("FindingsList", () => {
  it("links each finding to its write-up in a new tab, safely", () => {
    render(
      <FindingsList
        data={{
          findings: [
            {
              title: "Baseline comparison",
              url: "https://github.com/enkay-pixel/quantpulse/blob/main/docs/findings/baseline-comparison.md",
              question: "Does the model beat a one-line momentum rule?",
              outcome: "Not on the JSE.",
            },
          ],
        }}
      />,
    );
    const link = screen.getByRole("link", { name: "Baseline comparison" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.getByText("Not on the JSE.")).toBeInTheDocument();
  });
});

describe("ForwardVrpChart", () => {
  it("explains the empty state rather than drawing nothing", () => {
    render(<ForwardVrpChart data={{ exchange: "XJSE", days: [] }} />);
    expect(screen.getByText(/realization window has closed/)).toBeInTheDocument();
  });

  it("states the average premium and how many days it was positive", () => {
    const days = [
      { snapshot_date: "2026-07-20", tickers: 50, implied: 0.3, realized: 0.25, premium: 0.05 },
      { snapshot_date: "2026-07-21", tickers: 50, implied: 0.3, realized: 0.31, premium: -0.01 },
    ];
    render(<ForwardVrpChart data={{ exchange: "XNYS", days }} />);
    expect(screen.getByText("+2.0 points")).toBeInTheDocument();
    expect(screen.getByText(/above it on 1 of 2 days/)).toBeInTheDocument();
  });
});
