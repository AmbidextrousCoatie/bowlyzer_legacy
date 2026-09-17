import { describe, expect, test } from "vite-plus/test";
import {
  clutchFromV1,
  consistencyFromV1,
  historyFromV1,
  leagueComparisonFromV1,
  seasonsFromV1,
  specialMatchesFromV1,
  teamsFromV1,
} from "./teamV1";

const SAMPLE = {
  teams: ["EPA München 3", "Donaubowler Regensburg 2", ""],
  seasons: ["24/25", "25/26"],
  history: {
    "25/26": {
      league_name: "BZL S2",
      final_position: 6,
      statistics: {
        total_score: 18179,
        average_score: 151.49,
        games_played: 120,
        best_score: 223,
        worst_score: 94,
      },
    },
  },
  leagues: {
    "25/26": {
      league_name: "BZL S2",
      num_teams: 6,
      team_average: 151.49,
      league_average: 171.72,
      vs_league_average: -20.23,
      final_position: 6,
    },
  },
  clutch: {
    total_games: 40,
    total_clutch_games: 8,
    total_clutch_wins: 3,
    total_clutch_losses: 5,
    clutch_percentage: 37.5,
    opponent_clutch: { "Rival 1": { wins: 2, losses: 1 } },
  },
  consistency: {
    sample: 40,
    mean: 660.06,
    std: 85.74,
    cv_percent: 12.99,
    min: 398,
    max: 976,
    range: 578,
    iqr: 121,
    consistency_rating: "Average",
  },
  special_matches: {
    highest_scores: [
      {
        season: "25/26",
        league: "BZL S2",
        week: 5,
        round: 4,
        score: 753,
        opponent: "Rival 1",
        opponent_score: 523,
        win_margin: 230,
      },
    ],
    lowest_scores: [],
    biggest_win_margin: [],
    biggest_loss_margin: [],
  },
};

describe("teamV1 adapters", () => {
  test("lists team names", () => {
    expect(teamsFromV1(SAMPLE)).toEqual(["EPA München 3", "Donaubowler Regensburg 2"]);
  });

  test("fills league_level from the league name", () => {
    const history = historyFromV1(SAMPLE);
    expect(history["25/26"]).toMatchObject({
      league_name: "BZL S2",
      final_position: 6,
      league_level: 6,
    });
  });

  test("maps league comparison onto Flask-shaped nested averages", () => {
    const cmp = leagueComparisonFromV1(SAMPLE);
    expect(cmp["25/26"]).toMatchObject({
      league_name: "BZL S2",
      performance_rank: 6,
      vs_league_average: -20.23,
      league_averages: { average_score: 171.72, num_teams: 6 },
      team_performance: { team_average_score: 151.49, vs_league_average: -20.23, performance_rank: 6 },
    });
  });

  test("maps consistency kernel names onto SPA metrics", () => {
    expect(consistencyFromV1(SAMPLE)).toMatchObject({
      mean_score: 660.06,
      std_deviation: 85.74,
      coefficient_of_variation: 12.99,
      min_score: 398,
      max_score: 976,
      score_range: 578,
      iqr: 121,
      consistency_rating: "Average",
    });
    expect(consistencyFromV1({ consistency: { sample: 0 } }).error).toBe("No team data found");
  });

  test("maps special matches to Flask PascalCase rows", () => {
    expect(specialMatchesFromV1(SAMPLE).highest_scores?.[0]).toEqual({
      Season: "25/26",
      League: "BZL S2",
      Week: 5,
      Round: 4,
      Score: 753,
      Opponent: "Rival 1",
      OpponentScore: 523,
      WinMargin: 230,
    });
  });

  test("keeps clutch opponent map", () => {
    expect(seasonsFromV1(SAMPLE)).toEqual(["24/25", "25/26"]);
    expect(clutchFromV1(SAMPLE).opponent_clutch).toEqual({ "Rival 1": { wins: 2, losses: 1 } });
  });
});
