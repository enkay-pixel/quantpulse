import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { slugify, useHashTab } from "../hooks/useHashTab";

const TABS = ["Overview", "Evidence", "Options", "Model & Book"];

afterEach(() => {
  window.location.hash = "";
});

describe("slugify", () => {
  it("makes URL-safe slugs", () => {
    expect(slugify("Overview")).toBe("overview");
    expect(slugify("Model & Book")).toBe("model-book");
  });
});

describe("useHashTab", () => {
  it("defaults to the first tab with no hash", () => {
    const { result } = renderHook(() => useHashTab(TABS));
    expect(result.current[0]).toBe("Overview");
  });

  it("reads the initial tab from the hash", () => {
    window.location.hash = "evidence";
    const { result } = renderHook(() => useHashTab(TABS));
    expect(result.current[0]).toBe("Evidence");
  });

  it("writes the hash when a tab is selected", () => {
    const { result } = renderHook(() => useHashTab(TABS));
    act(() => result.current[1]("Model & Book"));
    expect(result.current[0]).toBe("Model & Book");
    expect(window.location.hash).toBe("#model-book");
  });

  it("falls back to the first tab for an unknown hash", () => {
    window.location.hash = "nonsense";
    const { result } = renderHook(() => useHashTab(TABS));
    expect(result.current[0]).toBe("Overview");
  });
});
