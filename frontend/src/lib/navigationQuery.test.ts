import { describe, expect, test } from "vite-plus/test";
import { linkForPath, searchParamsForPath } from "./navigationQuery";

describe("searchParamsForPath", () => {
  test("keeps myClub when navigating to another page", () => {
    const source = new URLSearchParams(
      "database=db_real_merged&myClub=1.+BC+Veitsh%C3%B6chheim&season=25%2F26&league=BayL",
    );
    const next = searchParamsForPath("/spieler", source);
    expect(next.get("myClub")).toBe("1. BC Veitshöchheim");
    expect(next.get("database")).toBe("db_real_merged");
    expect(next.has("league")).toBe(false);
    expect(next.has("season")).toBe(false);
  });
});

describe("linkForPath", () => {
  test("merges explicit params and preserves myClub", () => {
    const source = new URLSearchParams(
      "database=db_real_merged&myClub=Donaubowler+Regensburg",
    );
    const href = linkForPath("/liga", source, { season: "25/26", league: "BayL" });
    const qs = new URLSearchParams(href.split("?")[1] ?? "");
    expect(href.startsWith("/liga?")).toBe(true);
    expect(qs.get("myClub")).toBe("Donaubowler Regensburg");
    expect(qs.get("database")).toBe("db_real_merged");
    expect(qs.get("season")).toBe("25/26");
    expect(qs.get("league")).toBe("BayL");
  });

  test("preserves myClub on bare paths", () => {
    const source = new URLSearchParams("myClub=Test+Club&database=db_real_merged");
    expect(linkForPath("/spieler", source)).toBe(
      "/spieler?database=db_real_merged&myClub=Test+Club",
    );
  });
});
