import { describe, expect, test, vi } from "vite-plus/test";
import {
  ApiError,
  FLASK_UNAVAILABLE_MESSAGE,
  fetchJson,
  flaskQueryRetry,
  isFlaskUnavailableError,
  isFlaskUnavailableStatus,
} from "./api";

describe("Flask unavailable stub", () => {
  test("treats proxy gateway statuses as Flask-down", () => {
    expect(isFlaskUnavailableStatus(502)).toBe(true);
    expect(isFlaskUnavailableStatus(503)).toBe(true);
    expect(isFlaskUnavailableStatus(504)).toBe(true);
    expect(isFlaskUnavailableStatus(500)).toBe(false);
    expect(isFlaskUnavailableStatus(404)).toBe(false);
  });

  test("does not retry Flask-down errors", () => {
    const error = new ApiError(FLASK_UNAVAILABLE_MESSAGE, 502);
    expect(isFlaskUnavailableError(error)).toBe(true);
    expect(flaskQueryRetry(0, error)).toBe(false);
    expect(flaskQueryRetry(0, new Error("boom"))).toBe(true);
  });

  test("fetchJson maps 502 to the German stub", async () => {
    vi.stubGlobal(
      "fetch",
      async () => new Response("Bad Gateway", { status: 502, statusText: "Bad Gateway" }),
    );
    try {
      await expect(fetchJson("/pipeline/status")).rejects.toMatchObject({
        message: FLASK_UNAVAILABLE_MESSAGE,
        status: 502,
      });
    } finally {
      vi.unstubAllGlobals();
    }
  });

  test("fetchJson maps network failures to the German stub", async () => {
    vi.stubGlobal("fetch", async () => {
      throw new TypeError("Failed to fetch");
    });
    try {
      await expect(fetchJson("/pipeline/status")).rejects.toMatchObject({
        message: FLASK_UNAVAILABLE_MESSAGE,
        status: 503,
      });
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
