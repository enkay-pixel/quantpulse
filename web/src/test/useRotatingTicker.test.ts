import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { UniverseMember } from "../api/types";
import { priceTickers, useRotatingTicker } from "../hooks/useRotatingTicker";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("priceTickers", () => {
  const universe: UniverseMember[] = [
    { ticker: "SAP.DE", exchange: "XETR", asset_type: "stock", active: true },
    { ticker: "EXS1.DE", exchange: "XETR", asset_type: "etf", active: true },
    { ticker: "OLD.DE", exchange: "XETR", asset_type: "stock", active: false },
    { ticker: "NESN.SW", exchange: "XSWX", asset_type: "stock", active: true },
  ];

  it("cycles through the forecasts when the market has them", () => {
    expect(priceTickers(["NESN.SW"], universe, "XSWX")).toEqual(["NESN.SW"]);
  });

  it("falls back to the market's active stocks when it has no forecasts", () => {
    // Frankfurt's first model did not clear the gate (2026-10-28): its prices still show.
    expect(priceTickers([], universe, "XETR")).toEqual(["SAP.DE"]);
  });

  it("shows nothing while the forecasts are still loading", () => {
    expect(priceTickers(undefined, universe, "XETR")).toEqual([]);
  });
});

describe("useRotatingTicker", () => {
  it("starts on the first ticker and advances on each interval", () => {
    const { result } = renderHook(() =>
      useRotatingTicker(["A", "B", "C"], { rotateMs: 1000, pinMs: 5000 }),
    );
    expect(result.current.ticker).toBe("A");
    expect(result.current.isPinned).toBe(false);

    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.ticker).toBe("B");

    act(() => vi.advanceTimersByTime(2000));
    expect(result.current.ticker).toBe("A"); // wrapped past C
  });

  it("pins a manual pick, overriding rotation, then resumes after pinMs", () => {
    const { result } = renderHook(() =>
      useRotatingTicker(["A", "B", "C"], { rotateMs: 1000, pinMs: 3000 }),
    );
    act(() => result.current.pin("C"));
    expect(result.current.ticker).toBe("C");
    expect(result.current.isPinned).toBe(true);

    // still pinned partway through the window
    act(() => vi.advanceTimersByTime(2000));
    expect(result.current.ticker).toBe("C");
    expect(result.current.isPinned).toBe(true);

    // past the window: rotation resumes
    act(() => vi.advanceTimersByTime(2000));
    expect(result.current.isPinned).toBe(false);
    expect(["A", "B", "C"]).toContain(result.current.ticker);
  });

  it("returns null when there are no tickers", () => {
    const { result } = renderHook(() => useRotatingTicker([]));
    expect(result.current.ticker).toBeNull();
  });
});
