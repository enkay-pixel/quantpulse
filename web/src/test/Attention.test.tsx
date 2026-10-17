import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AttentionRow } from "../api/types";
import { AttentionChart } from "../components/AttentionChart";
import { AttentionTable, UNUSUAL, attentionVerdict } from "../components/AttentionTable";
import { visibleTabs } from "../lib/tabs";

function row(over: Partial<AttentionRow>): AttentionRow {
  return {
    ticker: "NPN.JO",
    followed_by: "model",
    article: "Naspers",
    date: "2026-10-15",
    views_7d: 280,
    baseline_90d: 265,
    attention_ratio: 280 / 265,
    ...over,
  };
}

describe("attentionVerdict", () => {
  it("says nothing is unusual, and that attention confirms more than it warns", () => {
    const text = attentionVerdict([row({}), row({ ticker: "SBK.JO", attention_ratio: 1.6, views_7d: 176 })]);
    expect(text).toMatch(/^Nothing here is drawing unusual attention/);
    expect(text).toMatch(/highest is SBK.JO/);
    expect(text).toMatch(/1.6× its usual/);
    expect(text).toMatch(/only 2.1× on the 22nd/);
  });

  it("names every stock at or above the mark, and still says what attention cannot tell", () => {
    const text = attentionVerdict([
      row({ ticker: "AAA", attention_ratio: UNUSUAL }),
      row({ ticker: "BBB", attention_ratio: 7.5 }),
      row({}),
    ]);
    expect(text).toMatch(/^2 of these 3 stocks/);
    expect(text).toMatch(/AAA, BBB|BBB, AAA/);
    expect(text).toMatch(/The most is BBB, at 7.5×/);
    expect(text).toMatch(/not which way it will move/);
  });

  it("does not invent a ratio while the history is too short", () => {
    expect(attentionVerdict([row({ attention_ratio: null, baseline_90d: null })])).toMatch(
      /still building/,
    );
  });
});

describe("AttentionTable", () => {
  it("ranks by attention and marks the unusual ones in words, not colour alone", () => {
    render(
      <AttentionTable
        data={{
          exchange: "XJSE",
          as_of: "2026-10-15",
          rows: [row({ ticker: "SBK.JO", attention_ratio: 1.2 }), row({ ticker: "MTN.JO", attention_ratio: 4.0 })],
        }}
        selected={null}
        onSelect={vi.fn()}
      />,
    );
    const order = screen.getAllByTestId(/^attention-/).map((el) => el.dataset.testid);
    expect(order).toEqual(["attention-MTN.JO", "attention-SBK.JO"]);
    expect(screen.getByText("unusual")).toBeInTheDocument();
  });
});

describe("AttentionChart", () => {
  it("says so when a stock has no history", () => {
    render(<AttentionChart data={{ ticker: "NPN.JO", article: null, days: [] }} />);
    expect(screen.getByText(/No page-view history for NPN.JO/)).toBeInTheDocument();
  });

  it("labels both lines and names the article the views came from", () => {
    render(
      <AttentionChart
        data={{
          ticker: "NPN.JO",
          article: "Naspers",
          days: [{ date: "2026-10-15", views: 300, views_7d: 280, baseline_90d: 265 }],
        }}
      />,
    );
    expect(screen.getByText("Views a day, past week")).toBeInTheDocument();
    expect(screen.getByText(/Usual \(90-day median/)).toBeInTheDocument();
    expect(screen.getByText("Wikipedia: Naspers")).toBeInTheDocument();
  });
});

describe("visibleTabs", () => {
  it("keeps Positioning on a market without option chains, and drops only Options", () => {
    const jse = visibleTabs(false);
    expect(jse).toContain("Positioning");
    expect(jse).not.toContain("Options");
    expect(visibleTabs(true)).toContain("Options");
    // Before the market list loads, nothing is hidden.
    expect(visibleTabs(undefined)).toContain("Options");
  });
});
