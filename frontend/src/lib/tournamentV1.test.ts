import { describe, expect, test } from "vite-plus/test";
import {
  formatFromV1,
  leaderboardTableFromV1,
  playerResultsFromV1,
  playerRoundTableFromV1,
  roundResultsTableFromV1,
} from "./tournamentV1";

describe("tournamentV1 adapters", () => {
  test("overall leaderboard expands round columns and net sort metadata", () => {
    const table = leaderboardTableFromV1(
      [
        {
          rank: 1,
          player_name: "Alpha",
          club: "Regensburg",
          round_1: 600,
          round_2: 580,
          total_score: 1180,
          avg_scratch: 196.7,
          total_net: 1240,
          avg_net: 206.7,
          handicap_display: 10,
        },
      ],
      {
        rounds: [
          { round_number: 1, round_name: "Quali" },
          { round_number: 2, round_name: "Final" },
        ],
        useNet: true,
      },
    );
    const fields = table.columns.flatMap((group) => group.columns?.map((col) => col.field) ?? []);
    expect(fields).toContain("round_1");
    expect(fields).toContain("round_2");
    expect(fields).toContain("total_net");
    expect(fields).toContain("avg_net");
    expect(table.data[0]).toMatchObject({ player: "Alpha", total_score: 1180 });
    expect(table.default_sort).toEqual({ field: "rank", dir: "asc" });
    expect(table.metadata).toMatchObject({ leaderboard_mode: "scratch_net_handicap" });
  });

  test("overall leaderboard with KO sorts by position, not pins", () => {
    const table = leaderboardTableFromV1(
      [
        { rank: 5, player: "Low place high pins", total_score: 2000 },
        { rank: 1, player: "Champion", total_score: 1500 },
      ],
      { koBracketFormat: "tree" },
    );
    expect(table.default_sort).toEqual({ field: "rank", dir: "asc" });
    expect(table.metadata).toMatchObject({ initial_sort: [{ field: "rank", dir: "asc" }] });
  });

  test("single-round leaderboard uses stage and cumulative totals", () => {
    const table = leaderboardTableFromV1(
      [
        {
          rank: 2,
          player: "Beta",
          round_score: 540,
          avg_score: 180,
          total_score: 1100,
          total_avg: 183.3,
        },
      ],
      { useNet: false },
    );
    const fields = table.columns.flatMap((group) => group.columns?.map((col) => col.field) ?? []);
    expect(fields).toContain("round_score");
    expect(fields).toContain("total_score");
    expect(fields).not.toContain("avg_net");
  });

  test("round results emit 0-based game heatmap fields", () => {
    const table = roundResultsTableFromV1([
      {
        overall_rank: 1,
        player_name: "Alpha",
        game_0: 200,
        game_1: 180,
        stage_score: 380,
        avg_score: 190,
        total_score: 380,
        overall_avg: 190,
      },
    ]);
    const fields = table.columns.flatMap((group) => group.columns?.map((col) => col.field) ?? []);
    expect(fields).toContain("game_0");
    expect(fields).toContain("game_1");
    expect(table.metadata).toMatchObject({
      heatmap_ranges: { game_score: { perfect_score: 300 } },
    });
  });

  test("player round table keeps stage and cumulative ranks", () => {
    const table = playerRoundTableFromV1([
      {
        stage: "Quali",
        game_0: 210,
        stage_score: 210,
        round_avg: 210,
        round_rank: 3,
        cum_score: 210,
        cum_avg: 210,
        cum_rank: 3,
      },
    ]);
    expect(table.data[0]).toMatchObject({ stage: "Quali", round_rank: 3, cum_rank: 3 });
  });

  test("format maps handicap bands", () => {
    const format = formatFromV1({
      round_count: 2,
      rounds: [{ round_number: 1, round_name: "Quali" }],
      handicap: {
        used: true,
        columns: { handicap: true, apriori_average: false, handicap_reference: false },
        pins: { kind: "uniform", value: 12 },
      },
    });
    expect(format.handicap?.used).toBe(true);
    expect(format.handicap?.pins).toEqual({ kind: "uniform", value: 12 });
    expect(format.config).toEqual({});
  });

  test("format and section pass KO fields through", () => {
    const format = formatFromV1({
      rounds: [{ round_number: 9, round_name: "KO-Finale", is_ko_finale_cluster: true }],
      ko_bracket_format: "seeded_elim_stepladder",
      ko_finale_series_label_de: "Finale inkl. Handicap",
    });
    expect(format.ko_bracket_format).toBe("seeded_elim_stepladder");
    expect(format.rounds?.[0]?.is_ko_finale_cluster).toBe(true);
    expect(format.ko_finale_series_label_de).toContain("Handicap");
  });

  test("player results unwrap named tournament rows", () => {
    const rows = playerResultsFromV1({
      results: [
        { season: "25/26", tournament: "NBM", position: 4, average: 198.2, club: "Regensburg" },
      ],
    });
    expect(rows[0]).toMatchObject({ season: "25/26", tournament: "NBM", position: 4 });
  });
});
