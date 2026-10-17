import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { BriefOut } from "../api/types";
import { AdvisorBrief } from "../components/AdvisorBrief";
import { visibleTabs } from "../lib/tabs";

const BRIEF: BriefOut = {
  ticker: "GME",
  name: null,
  exchange: "XNYS",
  followed_by: "watchlist",
  as_of: "2026-10-16",
  summary: "GME closed at $27.00 on 16 Oct 2026, +40% over the past year.",
  facts: [{ fact: "Sold short", value: "22.0% of the float", note: "Settled 30 Sep 2026." }],
  for_points: ["Insiders bought $99M of the stock on the open market in the past 90 days."],
  against_points: [],
  risks: ["It swings about 85% a year."],
  questions: ["What would buying and holding it cost me, in fees and in tax, where I live?"],
  limits: ["The model does not follow this name."],
  disclaimer: "An assessment of public evidence. It is not a recommendation to buy, sell or hold anything.",
};

describe("AdvisorBrief", () => {
  it("lays out each section under its plain name, and says so when one is empty", () => {
    render(<AdvisorBrief data={BRIEF} />);
    for (const heading of ["The evidence", "In its favour", "Against it", "Risks to raise", "Questions for your advisor", "What this cannot tell you"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    }
    expect(screen.getByText("Nothing in the evidence leans this way.")).toBeInTheDocument();
    expect(screen.getByText("watchlist")).toBeInTheDocument();
    expect(screen.getByText(/not a recommendation/)).toBeInTheDocument();
  });
});

describe("the Brief tab", () => {
  it("shows on both markets", () => {
    expect(visibleTabs(true)).toContain("Brief");
    expect(visibleTabs(false)).toContain("Brief");
  });
});
