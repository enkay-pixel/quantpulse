import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ExchangePicker } from "../components/ExchangePicker";
import type { Exchange } from "../api/types";

const XNYS: Exchange = {
  code: "XNYS", display_name: "New York", timezone: "America/New_York", currency: "USD",
  benchmark: "SPY", has_options: true, display_symbol: "$", display_divisor: 1, configured: true,
};
const XJSE: Exchange = {
  code: "XJSE", display_name: "Johannesburg", timezone: "Africa/Johannesburg", currency: "ZAc",
  benchmark: "STX40.JO", has_options: false, display_symbol: "R", display_divisor: 100,
  configured: true,
};

describe("ExchangePicker", () => {
  it("offers each configured market by name and shows the current one", () => {
    render(<ExchangePicker exchanges={[XNYS, XJSE]} selected="XJSE" onSelect={vi.fn()} />);
    expect(screen.getByRole("combobox", { name: "Market" })).toHaveValue("XJSE");
    expect(screen.getByRole("option", { name: "New York (XNYS)" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Johannesburg (XJSE)" })).toBeInTheDocument();
  });

  it("reports the chosen market", () => {
    const onSelect = vi.fn();
    render(<ExchangePicker exchanges={[XNYS, XJSE]} selected="XNYS" onSelect={onSelect} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Market" }), {
      target: { value: "XJSE" },
    });
    expect(onSelect).toHaveBeenCalledWith("XJSE");
  });

  it("holds seven markets in one control", () => {
    // The reason it is a menu: seven buttons do not fit a phone's width.
    const seven = ["XNYS", "XJSE", "XLON", "XETR", "XPAR", "XSWX", "XAMS"].map((code) => ({
      ...XNYS,
      code,
      display_name: `City ${code}`,
    }));
    render(<ExchangePicker exchanges={seven} selected="XAMS" onSelect={vi.fn()} />);
    expect(screen.getAllByRole("combobox")).toHaveLength(1);
    expect(screen.getAllByRole("option")).toHaveLength(7);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("hides markets with no data rather than offering an empty dashboard", () => {
    render(
      <ExchangePicker
        exchanges={[XNYS, { ...XJSE, configured: false }]}
        selected="XNYS"
        onSelect={vi.fn()}
      />,
    );
    // Only one market is usable, so there is nothing to switch between.
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("renders nothing when only one market exists", () => {
    const { container } = render(
      <ExchangePicker exchanges={[XNYS]} selected="XNYS" onSelect={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
