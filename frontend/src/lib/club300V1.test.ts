import { describe, expect, test } from "vite-plus/test";
import { club300FromV1 } from "./club300V1";

describe("club300FromV1", () => {
  test("maps named v1 games onto IndividualGameRecord fields", () => {
    const games = club300FromV1({
      club: "Donaubowler Regensburg",
      games: [
        {
          player: "Ada",
          player_id: "42",
          score: 300,
          date: "2024-05-12",
          season: "23/24",
          competition: "BayL",
          is_tournament: false,
          club: "Donaubowler Regensburg",
          team: "Donaubowler Regensburg 1",
          week: 5,
          round: 2,
        },
        {
          player_name: "Bea",
          score: 300,
          competition: "DM",
          is_tournament: true,
          round_number: 8,
        },
      ],
    });
    expect(games[0]).toMatchObject({
      player_name: "Ada",
      player_id: "42",
      score: 300,
      date: "2024-05-12",
      season: "23/24",
      competition: "BayL",
      is_tournament: false,
      club: "Donaubowler Regensburg",
      team_name: "Donaubowler Regensburg 1",
      team_number: 1,
      week: 5,
      round_number: 2,
    });
    expect(games[1]).toMatchObject({
      player_name: "Bea",
      is_tournament: true,
      round_number: 8,
    });
  });

  test("returns an empty list when games are missing", () => {
    expect(club300FromV1({})).toEqual([]);
    expect(club300FromV1([])).toEqual([]);
  });
});
