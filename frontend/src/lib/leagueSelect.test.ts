import { describe, expect, test } from "vite-plus/test";
import type { LeagueOption } from "../hooks/useLeague";
import { leagueInRegionScope } from "./leagueLevel";
import {
  groupLeaguesByLevel,
  leaguesForRegionSelect,
  leagueSelectDisplayLabel,
  leagueLevelSelectValue,
  leagueSelectValue,
  parseLeagueLevelParam,
  parseLeagueSelectValue,
  regionHasLeagues,
} from "./leagueSelect";

function opt(value: string, long_name = value): LeagueOption {
  return { value, short_name: value, long_name };
}

describe("leagueInRegionScope", () => {
  test("includes Bayernliga with both regions", () => {
    expect(leagueInRegionScope("BayL", "north")).toBe(true);
    expect(leagueInRegionScope("BayL (D)", "south")).toBe(true);
  });

  test("keeps only the selected Bereich otherwise", () => {
    expect(leagueInRegionScope("LL N1", "north")).toBe(true);
    expect(leagueInRegionScope("LL S", "north")).toBe(false);
    expect(leagueInRegionScope("KL S2", "south")).toBe(true);
  });
});

describe("leagueSelectValue", () => {
  test("prefers a concrete league over a region or level", () => {
    expect(leagueSelectValue("LL N1", "north", 4)).toBe("LL N1");
    expect(leagueSelectValue("", "south", null)).toBe("south");
    expect(leagueSelectValue("", "north", 4)).toBe(leagueLevelSelectValue(4));
    expect(leagueSelectValue("", "", null)).toBe("");
  });
});

describe("leagueSelectDisplayLabel", () => {
  const t = (_key: string, fallback?: string) => fallback ?? _key;
  const leagues = [opt("LL S", "Landesliga Süd")];

  test("uses Alle, region, level, then the league name", () => {
    expect(leagueSelectDisplayLabel("", leagues, t)).toBe("Alle");
    expect(leagueSelectDisplayLabel("north", leagues, t)).toBe("Norbereich");
    expect(leagueSelectDisplayLabel(leagueLevelSelectValue(4), leagues, t)).toBe("Landesliga");
    expect(leagueSelectDisplayLabel("LL S", leagues, t)).toBe("Landesliga Süd");
  });
});

describe("parseLeagueSelectValue", () => {
  test("maps Alle, Bereich, level, and a league id", () => {
    expect(parseLeagueSelectValue("")).toEqual({ league: "", division: "", level: null });
    expect(parseLeagueSelectValue("north")).toEqual({ league: "", division: "north", level: null });
    expect(parseLeagueSelectValue("level:4")).toEqual({ league: "", division: "", level: 4 });
    expect(parseLeagueSelectValue("A S1")).toEqual({ league: "A S1", division: "", level: null });
  });

  test("rejects unknown level tokens", () => {
    expect(parseLeagueLevelParam("99")).toBe(null);
    expect(parseLeagueSelectValue("level:99")).toEqual({ league: "", division: "", level: null });
  });
});

describe("leaguesForRegionSelect", () => {
  const leagues = [opt("LL S"), opt("A N1"), opt("BayL"), opt("KL N2")];

  test("lists every league by level when Alle is selected", () => {
    expect(leaguesForRegionSelect(leagues, "", "").map((item) => item.value)).toEqual([
      "BayL",
      "LL S",
      "KL N2",
      "A N1",
    ]);
  });

  test("keeps Bayernliga plus the selected region", () => {
    expect(leaguesForRegionSelect(leagues, "", "north").map((item) => item.value)).toEqual([
      "BayL",
      "KL N2",
      "A N1",
    ]);
  });

  test("does not shrink the list while a single league is selected", () => {
    expect(leaguesForRegionSelect(leagues, "LL S", "south").map((item) => item.value)).toEqual([
      "BayL",
      "LL S",
      "KL N2",
      "A N1",
    ]);
  });
});

describe("groupLeaguesByLevel", () => {
  test("uses Bayernliga / Landesliga headings", () => {
    const groups = groupLeaguesByLevel([opt("LL N1"), opt("BayL"), opt("BayL (D)")]);
    expect(groups.map((group) => group.label)).toEqual(["Bayernliga", "Landesliga"]);
    expect(groups[0]?.leagues.map((item) => item.value)).toEqual(["BayL", "BayL (D)"]);
  });
});

describe("regionHasLeagues", () => {
  test("counts Bayernliga as enough for both regions", () => {
    expect(regionHasLeagues([opt("BayL")], "north")).toBe(true);
    expect(regionHasLeagues([opt("LL S")], "north")).toBe(false);
  });
});
