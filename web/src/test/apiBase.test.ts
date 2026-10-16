import { describe, expect, it } from "vitest";

import { API_BASE } from "../api/client";

describe("API_BASE", () => {
  it("is same-origin by default, so the page works under any hostname it is opened with", () => {
    // An absolute default tied the page to the one origin the API allowed: opened at
    // 127.0.0.1 instead of localhost, every request was blocked while the API was healthy.
    expect(API_BASE).toBe("/api");
  });
});
