import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Tabs } from "../components/Tabs";

describe("Tabs", () => {
  it("marks the active tab and reports selection", () => {
    const onSelect = vi.fn();
    render(<Tabs tabs={["Overview", "Evidence"]} active="Overview" onSelect={onSelect} />);
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Evidence" })).toHaveAttribute("aria-selected", "false");
    fireEvent.click(screen.getByRole("tab", { name: "Evidence" }));
    expect(onSelect).toHaveBeenCalledWith("Evidence");
  });
});
