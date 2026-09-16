import { describe, expect, test } from "vite-plus/test";
import { TEAM_COLOR_PALETTES } from "./color-utils";
import { clubPlayerResultsFromV1 } from "./clubPlayerResultsV1";

describe("clubPlayerResultsFromV1", () => {
  test("maps named player rows onto the club results table", () => {
    const payload = clubPlayerResultsFromV1({
      club: "Donaubowler Regensburg",
      latest_season: "25/26",
      players: [
        {
          player: "Ada",
          player_id: "42",
          games: 120,
          average: 198.5,
          best_season: "24/25",
          best_season_average: 205.1,
          membership_seasons: 6,
          club_active: true,
        },
        {
          player_name: "Bea",
          games: 12,
          average: 160,
          club_active: false,
        },
      ],
    });
    expect(payload.club).toBe("Donaubowler Regensburg");
    expect(payload.table.columns.map((group) => group.title_key)).toEqual([
      "ui.team.club_player_group",
      "ui.team.club_alltime_group",
      "ui.team.club_best_season_group",
      "ui.team.club_membership_group",
    ]);
    expect(payload.table.data[0]).toMatchObject({
      rank: 1,
      player_name: "Ada",
      player_id: "42",
      games: 120,
      average: 198.5,
      best_season: "24/25",
      membership_seasons: 6,
      club_active: true,
    });
    expect(payload.table.row_metadata?.[0]).toEqual({
      rowAccentColor: TEAM_COLOR_PALETTES.rainbowPastel[2],
    });
    expect(payload.table.row_metadata?.[1]).toEqual({
      rowAccentColor: TEAM_COLOR_PALETTES.rainbowPastel[5],
    });
    expect(payload.table.metadata).toEqual({
      kind: "club_player_results",
      latest_season: "25/26",
    });
  });
});
