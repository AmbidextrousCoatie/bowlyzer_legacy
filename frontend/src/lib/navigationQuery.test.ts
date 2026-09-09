import { describe, expect, test } from "vite-plus/test";
import { linkForPath, searchParamsForPath } from "./navigationQuery";

describe("searchParamsForPath", () => {
  test("keeps myClub when navigating to another page", () => {
    const source = new URLSearchParams(
      "database=db_real_merged&myClub=1.+BC+Veitsh%C3%B6chheim&season=25%2F26&league=BayL&level=4",
    );
    const next = searchParamsForPath("/spieler", source);
    expect(next.get("myClub")).toBe("1. BC Veitshöchheim");
    expect(next.get("database")).toBe("db_real_merged");
    expect(next.has("league")).toBe(false);
    expect(next.has("level")).toBe(false);
    expect(next.get("season")).toBe("25/26");
  });
});

describe("linkForPath", () => {
  test("merges explicit params and preserves myClub", () => {
    const source = new URLSearchParams("database=db_real_merged&myClub=Donaubowler+Regensburg");
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
    const href = linkForPath("/spieler", source);
    const qs = new URLSearchParams(href.split("?")[1] ?? "");
    expect(href.startsWith("/spieler?")).toBe(true);
    expect(qs.get("database")).toBe("db_real_merged");
    expect(qs.get("myClub")).toBe("Test Club");
  });

  test("keeps story and beat across pages", () => {
    const source = new URLSearchParams("story=spieltag&beat=1&database=db_real_merged");
    const next = searchParamsForPath("/club", source);
    expect(next.get("story")).toBe("spieltag");
    expect(next.get("beat")).toBe("1");
    const href = linkForPath("/club", source, { club: "BC EMAX Unterföhring" });
    const qs = new URLSearchParams(href.split("?")[1] ?? "");
    expect(qs.get("story")).toBe("spieltag");
    expect(qs.get("beat")).toBe("1");
    expect(qs.get("club")).toBe("BC EMAX Unterföhring");
  });
});
