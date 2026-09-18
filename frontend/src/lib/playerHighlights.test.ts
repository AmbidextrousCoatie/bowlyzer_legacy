import { describe, expect, test } from "vite-plus/test";
import { buildPlayerHighlights } from "./playerHighlights";
import type { PlayerSeasonRow } from "../hooks/usePlayer";

describe("Clubzugehörigkeit highlights", () => {
  test("all-players rows put games in the metric and club in details", () => {
    const rows: PlayerSeasonRow[] = [
      {
        row_type: "competition",
        player_name: "Hartfeil, Volkmar",
        player_id: "7830",
        club: "Donaubowler Regensburg",
        history_club: "Donaubowler Regensburg",
        season: "09/10",
        games: 400,
        total_pins: 80000,
        average: 200,
      },
      {
        row_type: "competition",
        player_name: "Hartfeil, Volkmar",
        player_id: "7830",
        club: "Donaubowler Regensburg",
        history_club: "Donaubowler Regensburg",
        season: "10/11",
        games: 601,
        total_pins: 120200,
        average: 200,
      },
    ];
    const data = buildPlayerHighlights({
      scope: "all",
      seasons: [],
      playerCompetitions: rows,
    });
    expect(data.clubAffiliation[0]?.value).toBe("1001");
    expect(data.clubAffiliation[0]?.detail).toContain("Donaubowler Regensburg");
    expect(data.clubAffiliation[0]?.label).toBe("Hartfeil, Volkmar");
  });
});
