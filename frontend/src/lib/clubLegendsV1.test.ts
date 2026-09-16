import { describe, expect, test } from "vite-plus/test";
import { clubLegendsFromV1 } from "./clubLegendsV1";

describe("clubLegendsFromV1", () => {
  test("maps player to player_name and keeps highlight fields", () => {
    const payload = clubLegendsFromV1({
      club: "Donaubowler Regensburg",
      most_games: [
        {
          player: "Ada",
          player_id: "42",
          value: 120,
          games: 120,
          average: 198.5,
        },
      ],
      most_teams_represented: [{ player_name: "Ada", value: 2, teams: ["Basis", "2"] }],
    });
    expect(payload.club).toBe("Donaubowler Regensburg");
    expect(payload.most_games[0]).toMatchObject({
      player_id: "42",
      player_name: "Ada",
      value: 120,
      games: 120,
      average: 198.5,
    });
    expect(payload.most_teams_represented[0]?.teams).toEqual(["Basis", "2"]);
    expect(payload.most_seasons).toEqual([]);
  });
});
