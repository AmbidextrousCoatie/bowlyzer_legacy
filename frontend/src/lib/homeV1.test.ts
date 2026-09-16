import { describe, expect, test } from "vite-plus/test";
import { latestEventsFromV1, statsFromV1 } from "./homeV1";

const SAMPLE = {
  counts: {
    games: 12000,
    league_games: 9000,
    tournament_games: 3000,
    years: 16,
    league_seasons: 42,
    tournaments: 18,
    players: 510,
  },
  latest_events: [
    { season: "25/26", league: "Bayernliga", week: 4, date: "2026-09-12" },
    { season: "25/26", league: "Landesliga Nord", week: "3", date: "2026-09-05" },
    { season: "", league: "skip-me", week: 1, date: "2026-01-01" },
  ],
};

describe("homeV1 adapters", () => {
  test("maps named counts onto landing stats", () => {
    expect(statsFromV1(SAMPLE)).toEqual({
      games: 12000,
      league_games: 9000,
      tournament_games: 3000,
      years: 16,
      league_seasons: 42,
      tournaments: 18,
      players: 510,
    });
  });

  test("falls back to seasons when years is absent", () => {
    expect(statsFromV1({ counts: { seasons: 12, players: 3 } }).years).toBe(12);
  });

  test("maps latest events to Flask-shaped rows and drops blanks", () => {
    expect(latestEventsFromV1(SAMPLE)).toEqual([
      { Season: "25/26", League: "Bayernliga", Week: 4, Date: "2026-09-12" },
      { Season: "25/26", League: "Landesliga Nord", Week: 3, Date: "2026-09-05" },
    ]);
  });
});
