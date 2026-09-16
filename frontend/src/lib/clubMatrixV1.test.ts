import { describe, expect, test } from "vite-plus/test";
import { clubMatrixFromV1 } from "./clubMatrixV1";

describe("clubMatrixFromV1", () => {
  test("builds an empty catalog payload when no club is selected", () => {
    const payload = clubMatrixFromV1({
      clubs: ["Donaubowler Regensburg", "BC EMAX Unterföhring"],
      onlyUnnumbered: false,
      selectedClub: "",
    });
    expect(payload.selected_club).toBe("");
    expect(payload.matrix).toEqual({ club: "", seasons: [], rows: [] });
    expect(payload.clubs).toHaveLength(2);
    expect(payload.league_long_names).toEqual({});
  });

  test("keeps named history rows and indexes leagues for diagnosis links", () => {
    const payload = clubMatrixFromV1({
      clubs: ["Donaubowler Regensburg"],
      onlyUnnumbered: true,
      selectedClub: "donaubowler",
      history: {
        club: "Donaubowler Regensburg",
        seasons: ["25/26"],
        rows: [
          {
            team_number: "base",
            seasons: {
              "25/26": {
                items: [{ league: "BayL", final_position: 3, team_count: 8 }],
              },
            },
          },
        ],
      },
    });
    expect(payload.selected_club).toBe("Donaubowler Regensburg");
    expect(payload.only_unnumbered).toBe(true);
    expect(payload.matrix.rows[0]?.team_number).toBe("base");
    expect(payload.league_long_names).toEqual({ BayL: "BayL" });
  });
});
