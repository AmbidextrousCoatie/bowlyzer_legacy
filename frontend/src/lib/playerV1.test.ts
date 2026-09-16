import { describe, expect, test } from "vite-plus/test";
import {
  highestGamesFromV1,
  playerSearchFromV1,
  playerSeasonsFromV1,
  playerStatsFromV1,
} from "./playerV1";

describe("playerV1 adapters", () => {
  test("unwraps the player catalog", () => {
    const players = playerSearchFromV1({
      players: [
        { id: "7830", name: "Hartfeil, C" },
        { player_id: "25314", player_name: "Reasoner, M" },
        { name: "" },
      ],
    });
    expect(players).toEqual([
      { id: "7830", name: "Hartfeil, C", aliases: [] },
      { id: "25314", name: "Reasoner, M", aliases: [] },
    ]);
  });

  test("collapses duplicate catalog ids onto one row", () => {
    const players = playerSearchFromV1({
      players: [
        { id: "7830", name: "Hartfeil, Volkmar", aliases: ["Hartfeil , Volkmar"] },
        { id: "7830", name: "Hartfeil-Ave, Volkmar" },
      ],
    });
    expect(players).toEqual([
      {
        id: "7830",
        name: "Hartfeil, Volkmar",
        aliases: ["Hartfeil , Volkmar", "Hartfeil-Ave, Volkmar"],
      },
    ]);
  });

  test("unwraps season lists", () => {
    expect(playerSeasonsFromV1({ seasons: ["24/25", "25/26", ""] })).toEqual(["24/25", "25/26"]);
  });

  test("maps lifetime stats onto the SPA payload", () => {
    const stats = playerStatsFromV1({
      scope: "all",
      lifetime: {
        total_games: 12,
        total_pins: 2400,
        average_score: 200,
        best_game: { score: 279, event: "BayL", date: "2024-01-02" },
        best_season: { season: "24/25", average: 201.5, player_name: "Ada" },
        most_improved: { season: "25/26", improvement: 8.2, player_name: "Bea" },
      },
      seasons: [
        {
          season: "24/25",
          competition: "All Events",
          row_type: "season_total",
          games: 12,
          total_pins: 2400,
          average: 200,
        },
      ],
      periods: [{ season: "24/25", period_kind: "week", period_number: 3, games: 4, average: 198 }],
      player_competitions: [
        {
          season: "24/25",
          competition: "DM",
          is_tournament: true,
          player_name: "Ada",
          rank: 2,
          competitors: 48,
        },
        {
          row_type: "club_total",
          club: "Donaubowler Regensburg",
          games: 120,
          total_pins: 24000,
          average: 200,
        },
      ],
      player_season_totals: [{ season: "24/25", player_name: "Ada", average: 201.5, games: 8 }],
    });
    expect(stats?.scope).toBe("all");
    expect(stats?.lifetime).toMatchObject({
      total_games: 12,
      average_score: 200,
      best_game: { score: 279, event: "BayL" },
      best_season: { season: "24/25", player_name: "Ada" },
      most_improved: { improvement: 8.2, player_name: "Bea" },
    });
    expect(stats?.seasons?.[0]).toMatchObject({ row_type: "season_total", games: 12 });
    expect(stats?.player_competitions?.[0]).toMatchObject({
      is_tournament: true,
      rank: 2,
      competitors: 48,
    });
    expect(stats?.player_competitions?.[1]).toMatchObject({
      row_type: "club_total",
      club: "Donaubowler Regensburg",
      games: 120,
    });
  });

  test("maps highest-game rows", () => {
    const games = highestGamesFromV1({
      games: [
        {
          player_name: "Ada",
          player_id: "1",
          score: 300,
          date: "2024-05-12",
          competition: "BayL",
          is_tournament: false,
          team: "Donaubowler Regensburg 2",
          week: 4,
        },
      ],
    });
    expect(games[0]).toMatchObject({
      player_name: "Ada",
      score: 300,
      team_name: "Donaubowler Regensburg 2",
      team_number: 2,
      week: 4,
    });
  });
});
