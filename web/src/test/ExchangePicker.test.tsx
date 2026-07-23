import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ExchangePicker } from "../components/ExchangePicker";
import type { Exchange } from "../api/types";

const XNYS: Exchange = {
  code: "XNYS", timezone: "America/New_York", currency: "USD", benchmark: "SPY",
  has_options: true, display_symbol: "$", display_divisor: 1, configured: true,
};
const XJSE: Exchange = {
  code: "XJSE", timezone: "Africa/Johannesburg", currency: "ZAc", benchmark: "STX40.JO",
  has_options: false, display_symbol: "R", display_divisor: 100, configured: true,
};

describe("ExchangePicker", () => {
  it("offers each configured market and marks the current one", () => {
    render(<ExchangePicker exchanges={[XNYS, XJSE]} selected="XJSE" onSelect={vi.fn()} />);
    expect(screen.getByRole("button", { name: "XNYS" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "XJSE" })).toHaveAttribute("aria-pressed", "true");
  });

  it("reports the chosen market", () => {
    const onSelect = vi.fn();
    render(<ExchangePicker exchanges={[XNYS, XJSE]} selected="XNYS" onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: "XJSE" }));
    expect(onSelect).toHaveBeenCalledWith("XJSE");
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
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });

  it("renders nothing when only one market exists", () => {
    const { container } = render(
      <ExchangePicker exchanges={[XNYS]} selected="XNYS" onSelect={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
