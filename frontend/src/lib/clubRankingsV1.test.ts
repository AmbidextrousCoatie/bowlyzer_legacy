import { describe, expect, test } from "vite-plus/test";
import { clubRankingsFromV1 } from "./clubRankingsV1";

describe("clubRankingsFromV1", () => {
  test("stringifies week/round and keeps match context fields", () => {
    const payload = clubRankingsFromV1({
      top_n: 5,
      highest_total_pinfall: [{ club: "Club A", value: 12000 }],
      highest_team_game_average: [
        {
          club: "Club B",
          team: "Club B 1",
          season: "25/26",
          league: "BayL",
          week: 2,
          round: 1,
          value: 280.5,
          match_total: 560,
        },
      ],
    });
    expect(payload.highest_total_pinfall[0]).toEqual({
      club: "Club A",
      value: 12000,
      team: undefined,
      season: undefined,
      league: undefined,
      week: undefined,
      round: undefined,
      match_total: undefined,
    });
    expect(payload.highest_team_game_average[0]).toMatchObject({
      club: "Club B",
      team: "Club B 1",
      season: "25/26",
      league: "BayL",
      week: "2",
      round: "1",
      value: 280.5,
      match_total: 560,
    });
    expect(payload.most_members).toEqual([]);
    expect(payload.most_league_wins).toEqual([]);
  });
});
