import { describe, expect, test } from "vite-plus/test";
import {
  buildLeagueNavPath,
  matchupNavFromMetadata,
  opponentFromTeamVsTeamField,
  resolveAveragesCellNavPath,
  resolveLeagueCellNavPath,
  resolveTeamVsTeamCellNavPath,
  type LeagueNavContext,
} from "./leagueNavigation";
import type { ColumnGroup } from "./datatable/types";

const ctx = (overrides: Partial<LeagueNavContext> = {}): LeagueNavContext => ({
  season: "25/26",
  league: "BayL",
  defaultWeek: 6,
  sourceQuery: "database=db_real_merged",
  ...overrides,
});

const standingsColumns: ColumnGroup[] = [
  { title: "Ranking", columns: [{ field: "pos" }, { field: "team" }] },
  { title: "Saison", columns: [{ field: "season_points" }] },
  { title: "Spieltag 3", columns: [{ field: "week3_points" }] },
];

describe("buildLeagueNavPath", () => {
  test("keeps database and myClub while replacing liga drill-down keys", () => {
    const href = buildLeagueNavPath(
      { view: "league-team", team: "Donaubowler Regensburg 2" },
      ctx({ sourceQuery: "database=db_real_merged&myClub=Donaubowler+Regensburg&week=4&team=Other" }),
    );
    const qs = new URLSearchParams(href.split("?")[1] ?? "");
    expect(href.startsWith("/liga?")).toBe(true);
    expect(qs.get("database")).toBe("db_real_merged");
    expect(qs.get("myClub")).toBe("Donaubowler Regensburg");
    expect(qs.get("season")).toBe("25/26");
    expect(qs.get("league")).toBe("BayL");
    expect(qs.get("team")).toBe("Donaubowler Regensburg 2");
    expect(qs.has("week")).toBe(false);
    expect(qs.has("round")).toBe(false);
  });
});

describe("resolveLeagueCellNavPath", () => {
  test("ranking cells add the team filter without forcing a week", () => {
    const path = resolveLeagueCellNavPath("team", 0, "1. BC Veitshöchheim", standingsColumns, ctx());
    const qs = new URLSearchParams(path?.split("?")[1] ?? "");
    expect(qs.get("team")).toBe("1. BC Veitshöchheim");
    expect(qs.get("league")).toBe("BayL");
    expect(qs.has("week")).toBe(false);
    expect(qs.get("database")).toBe("db_real_merged");
  });

  test("ranking cells keep the current week on matchday tables", () => {
    const path = resolveLeagueCellNavPath(
      "pos",
      0,
      "1. BC Veitshöchheim",
      standingsColumns,
      ctx({ week: 6 }),
    );
    const qs = new URLSearchParams(path?.split("?")[1] ?? "");
    expect(qs.get("team")).toBe("1. BC Veitshöchheim");
    expect(qs.get("week")).toBe("6");
  });

  test("season totals drop team and week", () => {
    const path = resolveLeagueCellNavPath("season_points", 1, "Team A", standingsColumns, ctx({ week: 6 }));
    const qs = new URLSearchParams(path?.split("?")[1] ?? "");
    expect(qs.get("league")).toBe("BayL");
    expect(qs.has("week")).toBe(false);
    expect(qs.has("team")).toBe(false);
  });

  test("weekly columns set the week filter", () => {
    const path = resolveLeagueCellNavPath("week3_points", 2, "Team A", standingsColumns, ctx());
    const qs = new URLSearchParams(path?.split("?")[1] ?? "");
    expect(qs.get("week")).toBe("3");
    expect(qs.has("team")).toBe(false);
  });
});

describe("resolveAveragesCellNavPath", () => {
  test("adds the row team on season averages", () => {
    const path = resolveAveragesCellNavPath("BC EMAX Unterföhring", ctx());
    const qs = new URLSearchParams(path?.split("?")[1] ?? "");
    expect(qs.get("team")).toBe("BC EMAX Unterföhring");
    expect(qs.has("week")).toBe(false);
  });

  test("keeps matchday week when adding the team", () => {
    const path = resolveAveragesCellNavPath("BC EMAX Unterföhring", ctx({ week: 6 }));
    const qs = new URLSearchParams(path?.split("?")[1] ?? "");
    expect(qs.get("team")).toBe("BC EMAX Unterföhring");
    expect(qs.get("week")).toBe("6");
  });
});

describe("team vs team matrix navigation", () => {
  test("parses opponent names from score and points fields", () => {
    expect(opponentFromTeamVsTeamField("Donaubowler Regensburg 2_score")).toBe(
      "Donaubowler Regensburg 2",
    );
    expect(opponentFromTeamVsTeamField("Donaubowler Regensburg 2_points")).toBe(
      "Donaubowler Regensburg 2",
    );
    expect(opponentFromTeamVsTeamField("avg_score")).toBeNull();
    expect(opponentFromTeamVsTeamField("team")).toBeNull();
  });

  test("unique round adds the game filter", () => {
    const metadata = {
      matchups: {
        "Team A": { "Team B": { week: 6, round: 2 } },
      },
    };
    const path = resolveTeamVsTeamCellNavPath("Team B_score", "Team A", 812, metadata, ctx({ week: 6 }));
    const qs = new URLSearchParams(path?.split("?")[1] ?? "");
    expect(qs.get("week")).toBe("6");
    expect(qs.get("round")).toBe("2");
    expect(qs.get("team")).toBe("Team A");
    expect(matchupNavFromMetadata(metadata, "Team A", "Team B")).toEqual({ week: 6, round: 2 });
  });

  test("season matchup without a unique round uses the latest week", () => {
    const metadata = {
      matchups: {
        "Team A": { "Team B": { week: 4 } },
      },
    };
    const path = resolveTeamVsTeamCellNavPath("Team B_points", "Team A", 3.5, metadata, ctx());
    const qs = new URLSearchParams(path?.split("?")[1] ?? "");
    expect(qs.get("week")).toBe("4");
    expect(qs.get("team")).toBe("Team A");
    expect(qs.has("round")).toBe(false);
  });

  test("empty opponent cells do not navigate", () => {
    const path = resolveTeamVsTeamCellNavPath("Team B_score", "Team A", "", { matchups: {} }, ctx());
    expect(path).toBeNull();
  });
});
