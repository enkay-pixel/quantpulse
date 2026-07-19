import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QuintileChart } from "../components/QuintileChart";

describe("QuintileChart", () => {
  it("shows an empty state before the first transform run", () => {
    render(<QuintileChart quintiles={{ overall: [], recent: [] }} />);
    expect(screen.getByText(/Appears after the first dbt transform run/)).toBeInTheDocument();
  });

  it("renders the window toggle when data exists", () => {
    const stats = [1, 2, 3, 4, 5].map((q) => ({
      signal_quintile: q,
      n_days: 100,
      avg_next_day_return: (6 - q) / 10_000,
    }));
    render(<QuintileChart quintiles={{ overall: stats, recent: stats }} />);
    expect(screen.getByRole("button", { name: "All history" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Last ~30d" })).toBeInTheDocument();
  });
});
