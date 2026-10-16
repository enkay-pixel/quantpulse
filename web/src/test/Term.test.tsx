import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Term } from "../components/Term";

describe("Term", () => {
  it("shows the plain name, the technical name small, and what it means on hover", () => {
    render(<Term id="holdout_ic" />);
    expect(screen.getByText("Ranking accuracy")).toBeInTheDocument();
    expect(screen.getByText("holdout IC")).toBeInTheDocument();
    const help = screen.getByText("Ranking accuracy").closest("[title]")?.getAttribute("title");
    expect(help).toMatch(/rank correlation/);
    expect(help).toMatch(/How to read it: 0 is no better than chance/);
  });

  it("lets the context sharpen the name without losing the explanation", () => {
    render(<Term id="total_return" label="Live return" />);
    expect(screen.getByText("Live return")).toBeInTheDocument();
    expect(screen.getByText("Live return").closest("[title]")?.getAttribute("title")).toMatch(
      /gain or loss over the whole period/,
    );
  });

  it("refuses a term with no glossary entry rather than rendering it unexplained", () => {
    expect(() => render(<Term id="not_a_term" />)).toThrow(/No glossary entry/);
  });
});
