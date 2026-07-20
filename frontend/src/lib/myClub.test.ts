import { describe, expect, test } from "vite-plus/test";
import type { ClubMatrixPayload } from "../hooks/useLeague";
import { leaguesForSeason, participationFromClubMatrix } from "./myClub";

function payload(rows: ClubMatrixPayload["matrix"]["rows"]): ClubMatrixPayload {
  return {
    clubs: ["Donaubowler Regensburg"],
    selected_club: "Donaubowler Regensburg",
    only_unnumbered: false,
    matrix: {
      club: "Donaubowler Regensburg",
      seasons: ["24/25", "25/26"],
      rows,
    },
    league_long_names: {},
  };
}

describe("participationFromClubMatrix", () => {
  test("collects seasons and leagues from matrix cells", () => {
    const part = participationFromClubMatrix(
      payload([
        {
          team_number: "1",
          seasons: {
            "25/26": {
              leagues: "BayL",
              items: [{ league: "BayL" }],
            },
            "24/25": {
              leagues: "BZOL S1",
              items: [{ league: "BZOL S1" }],
            },
          },
        },
        {
          team_number: "2",
          seasons: {
            "25/26": {
              leagues: "Bezirksliga",
              items: [{ league: "Bezirksliga" }],
            },
          },
        },
      ]),
    );
    expect(part?.seasons).toEqual(["24/25", "25/26"]);
    expect(part?.leagues).toEqual(["BZOL S1", "BayL", "Bezirksliga"]);
    expect(leaguesForSeason(part, "25/26")).toEqual(["BayL", "Bezirksliga"]);
  });

  test("returns empty participation for empty matrix", () => {
    const part = participationFromClubMatrix(payload([]));
    expect(part?.seasons).toEqual([]);
    expect(part?.leagues).toEqual([]);
    expect(part?.leaguesBySeason.size).toBe(0);
  });
});
