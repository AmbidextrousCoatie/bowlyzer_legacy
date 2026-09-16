import { describe, expect, test } from "vite-plus/test";
import {
  classicDetailsTableFromV1,
  compareTableFromV1,
  gameOverviewTableFromV1,
  individualAveragesTableFromV1,
  recordsChartFromV1,
  seriesToTeamSeries,
  standingsTableFromV1,
  timetableFromV1,
} from "./leagueV1";

describe("leagueV1 adapters", () => {
  test("standings history expands week columns", () => {
    const table = standingsTableFromV1(
      [
        {
          rank: 1,
          team: "Alpha",
          points: 12.5,
          pins: 2400,
          average: 180.2,
          weeks: {
            1: { points: 4, pins: 800, average: 175 },
            2: { points: 8.5, pins: 1600, average: 185 },
          },
        },
      ],
      { history: true },
    );
    const fields = table.columns.flatMap((group) => group.columns?.map((col) => col.field) ?? []);
    expect(fields).toContain("week1_points");
    expect(fields).toContain("week2_avg");
    expect(table.data[0]).toMatchObject({
      pos: 1,
      team: "Alpha",
      season_points: 12.5,
      week1_score: 800,
      week2_points: 8.5,
    });
  });

  test("points series accumulates and sorts by total", () => {
    const series = seriesToTeamSeries({ Alpha: [1, 2], Beta: [4, 0] }, { accumulate: true });
    expect(series.data_accumulated).toEqual({ Alpha: [1, 3], Beta: [4, 4] });
    expect(series.sorted_by_total?.[0]).toBe("Beta");
  });

  test("timetable maps named weeks onto table rows", () => {
    const table = timetableFromV1({
      weeks: [{ week: 3, date: "2026-01-12", location: "Regensburg", status: "completed" }],
    });
    expect(table.data[0]).toMatchObject({
      week: 3,
      date: "2026-01-12",
      location: "Regensburg",
      status: "completed",
    });
  });

  test("compare matrix uses standings order and team-keyed cells", () => {
    const table = compareTableFromV1({
      teams: ["Alpha", "Beta"],
      cells: [{ team: "Alpha", opponent: "Beta", avg_pins: 900, avg_points: 4.5, week: 2 }],
    });
    expect(table.data[0]).toMatchObject({
      pos: 1,
      team: "Alpha",
      Beta_score: 900,
      Beta_points: 4.5,
    });
    expect(
      (table.metadata as { matchups: { Alpha: { Beta: { week: number } } } }).matchups.Alpha.Beta
        .week,
    ).toBe(2);
  });

  test("classic details emit gameN score columns", () => {
    const table = classicDetailsTableFromV1({
      view: "classic",
      players: [
        {
          player: "Ada",
          position: 0,
          total_score: 360,
          total_points: 4,
          average: 180,
          games: [
            { round: 1, opponent: "Beta", score: 180, points: 2 },
            { round: 2, opponent: "Gamma", score: 180, points: 2 },
          ],
        },
      ],
    });
    expect(table.data[0]).toMatchObject({
      position: 1,
      name: "Ada",
      game1_score: 180,
      game2_points: 2,
    });
  });

  test("game overview pairs team and opponent rows", () => {
    const table = gameOverviewTableFromV1(
      [
        { round: 1, team: "Alpha", opponent: "Beta", team_pins: 800, team_points: 6 },
        { round: 1, team: "Beta", opponent: "Alpha", team_pins: 760, team_points: 2 },
      ],
      [
        { rank: 1, team: "Alpha" },
        { rank: 2, team: "Beta" },
      ],
      1,
    );
    expect(table.data).toHaveLength(1);
    expect(table.data[0]).toMatchObject({
      team_name: "Alpha",
      team_position: 1,
      opponent_name: "Beta",
      opponent_pins: 760,
    });
  });

  test("individual averages keep Flask field names", () => {
    const table = individualAveragesTableFromV1([
      { player: "Ada", team: "Alpha", games: 8, pins: 1440, average: 180, high_game: 220 },
    ]);
    expect(table.data[0]).toMatchObject({ player: "Ada", total_points: 1440, high_game: 220 });
  });

  test("records chart uses season labels", () => {
    const chart = recordsChartFromV1(
      [
        { season: "24/25", average: 178.2 },
        { season: "25/26", average: 181 },
      ],
      "average",
      "League Average",
      "Average Score",
    );
    expect(chart.seasons).toEqual(["24/25", "25/26"]);
    expect(chart.data["League Average"]).toEqual([178.2, 181]);
  });
});
