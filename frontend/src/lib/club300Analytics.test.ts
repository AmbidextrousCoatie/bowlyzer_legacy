import { describe, expect, test } from "vite-plus/test";
import type { IndividualGameRecord } from "../hooks/usePlayer";
import { buildClub300HonorRoll, buildClub300Summary, formatClub300Date } from "./club300Analytics";

function game(overrides: Partial<IndividualGameRecord>): IndividualGameRecord {
  return {
    player_name: "Alpha, A",
    player_id: "1",
    score: 300,
    date: "2024-05-12",
    season: "23/24",
    competition: "BayL",
    is_tournament: false,
    ...overrides,
  };
}

describe("club300 honor roll", () => {
  test("groups by player_id, ranks by count, keeps newest game first", () => {
    const games = [
      game({ player_name: "Beta, B", player_id: "2", date: "2024-05-12" }),
      game({ player_name: "Alpha, A", player_id: "1", date: "2024-04-01" }),
      game({ player_name: "Alpha, A", player_id: "1", date: "2023-11-02" }),
      game({ player_name: "Alpha, A", player_id: "1", date: "2023-09-01" }),
    ];

    const honor = buildClub300HonorRoll(games);
    expect(honor).toHaveLength(2);
    expect(honor[0]).toMatchObject({ name: "Alpha, A", count: 3, rank: 1 });
    expect(honor[0]?.games.map((row) => row.date)).toEqual([
      "2024-04-01",
      "2023-11-02",
      "2023-09-01",
    ]);
    expect(honor[1]).toMatchObject({ name: "Beta, B", count: 1, rank: 2 });
  });

  test("tied counts share a dense rank", () => {
    const games = [
      game({ player_name: "Zed, Z", player_id: "z", date: "2024-01-02" }),
      game({ player_name: "Ann, A", player_id: "a", date: "2024-01-01" }),
    ];
    const honor = buildClub300HonorRoll(games);
    expect(honor.map((row) => [row.name, row.rank, row.count])).toEqual([
      ["Ann, A", 1, 1],
      ["Zed, Z", 1, 1],
    ]);
  });

  test("summary counts games, members, repeaters and latest", () => {
    const games = [
      game({ player_name: "Alpha, A", player_id: "1", date: "2024-05-12" }),
      game({ player_name: "Alpha, A", player_id: "1", date: "2023-09-01" }),
      game({ player_name: "Beta, B", player_id: "2", date: "2022-01-01" }),
    ];
    const summary = buildClub300Summary(games);
    expect(summary.gameCount).toBe(3);
    expect(summary.playerCount).toBe(2);
    expect(summary.repeaterCount).toBe(1);
    expect(summary.recordCount).toBe(2);
    expect(summary.recordHolders.map((row) => row.name)).toEqual(["Alpha, A"]);
    expect(summary.latest?.date).toBe("2024-05-12");
  });
});

describe("formatClub300Date", () => {
  test("turns ISO dates into German day.month.year", () => {
    expect(formatClub300Date("2024-05-12")).toBe("12.05.2024");
    expect(formatClub300Date("")).toBe("—");
    expect(formatClub300Date("12.05.2024")).toBe("12.05.2024");
  });
});
