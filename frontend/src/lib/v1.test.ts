import { describe, expect, test } from "vite-plus/test";
import { buildV1Url } from "./v1";

describe("buildV1Url", () => {
  test("omits empty, null, false, and undefined params", () => {
    expect(
      buildV1Url("/api/v1/clubs", {
        club: "",
        season: undefined,
        unnumbered: false,
        extra: null,
      }),
    ).toBe("/api/v1/clubs");
  });

  test("encodes season slashes in the query string", () => {
    expect(buildV1Url("/api/v1/leagues/standings", { season: "25/26", league: "BayL" })).toBe(
      "/api/v1/leagues/standings?season=25%2F26&league=BayL",
    );
  });

  test("sends true flags as 1", () => {
    expect(buildV1Url("/api/v1/clubs", { unnumbered: true })).toBe("/api/v1/clubs?unnumbered=1");
  });
});
