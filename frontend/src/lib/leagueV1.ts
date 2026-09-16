import type {
  HonorScores,
  LeagueHistoryChart,
  LeagueOption,
  SeasonLeagueStandings,
  TeamAnalysis,
  TeamSeriesPayload,
} from "../hooks/useLeague";
import type { ColumnDef, ColumnGroup, TableData } from "./datatable/types";
import { fetchV1 } from "./v1";

type Dict = Record<string, unknown>;

function asRecord(value: unknown): Dict {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Dict) : {};
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asStr(value: unknown): string {
  if (value == null) return "";
  return String(value).trim();
}

function asNum(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

function displayPos(value: unknown): number | null {
  const n = asNum(value);
  if (n == null) return null;
  return n + 1;
}

function fieldToken(value: string): string {
  const token = value.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  return token || "player";
}

function col(partial: ColumnDef): ColumnDef {
  return partial;
}

function group(title: string, columns: ColumnDef[], extra: Partial<ColumnGroup> = {}): ColumnGroup {
  return { title, columns, ...extra };
}

function table(
  columns: ColumnGroup[],
  data: Array<Record<string, unknown>>,
  extra: Partial<TableData> = {},
): TableData {
  return { columns, data, ...extra };
}

function playerKey(row: Dict): string {
  return asStr(row.player_id) || asStr(row.player) || asStr(row.key);
}

export function catalogFromV1(raw: unknown): {
  seasons: string[];
  leagues: LeagueOption[];
  weeks: number[];
  teams: string[];
  rounds: number[];
} {
  const rec = asRecord(raw);
  return {
    seasons: asList(rec.seasons).map(asStr).filter(Boolean),
    leagues: asList(rec.leagues).map((item) => {
      const row = asRecord(item);
      const value = asStr(row.value || row.short_name || row.league);
      return {
        short_name: asStr(row.short_name || value),
        long_name: asStr(row.long_name || row.short_name || value),
        value,
      };
    }),
    weeks: asList(rec.weeks)
      .map(asNum)
      .filter((n): n is number => n != null),
    teams: asList(rec.teams).map(asStr).filter(Boolean),
    rounds: asList(rec.rounds)
      .map(asNum)
      .filter((n): n is number => n != null),
  };
}

export function honorFromV1(raw: unknown): HonorScores {
  const rec = asRecord(raw);
  return {
    individual_scores: asList(rec.individual_scores) as HonorScores["individual_scores"],
    team_scores: asList(rec.team_scores) as HonorScores["team_scores"],
    individual_averages: asList(rec.individual_averages) as HonorScores["individual_averages"],
    team_averages: asList(rec.team_averages) as HonorScores["team_averages"],
  };
}

export function standingsTableFromV1(rows: unknown, options?: { history?: boolean }): TableData {
  const list = asList(rows).map(asRecord);
  const weeks = new Set<number>();
  if (options?.history) {
    for (const row of list) {
      const hist = asRecord(row.weeks);
      for (const key of Object.keys(hist)) {
        const n = asNum(key);
        if (n != null) weeks.add(n);
      }
    }
  }
  const weekNums = [...weeks].sort((a, b) => a - b);
  const columns: ColumnGroup[] = [
    group(
      "",
      [
        col({
          title: "#",
          title_key: "position",
          field: "pos",
          width: "50px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Mannschaft",
          title_key: "team",
          field: "team",
          width: "180px",
          align: "left",
        }),
      ],
      { frozen: "left" },
    ),
    group("Saison", [
      col({
        title: "Punkte",
        title_key: "points",
        field: "season_points",
        width: "80px",
        align: "center",
        decimal_places: 1,
      }),
      col({
        title: "Pins",
        title_key: "pins",
        field: "season_score",
        width: "80px",
        align: "center",
        decimal_places: 0,
      }),
      col({
        title: "Schnitt",
        title_key: "average",
        field: "season_avg",
        width: "80px",
        align: "center",
        decimal_places: 1,
      }),
    ]),
  ];
  for (const week of weekNums) {
    columns.push(
      group(String(week), [
        col({
          title: "Punkte",
          title_key: "points",
          field: `week${week}_points`,
          width: "70px",
          decimal_places: 1,
        }),
        col({
          title: "Pins",
          title_key: "score",
          field: `week${week}_score`,
          width: "70px",
          decimal_places: 0,
        }),
        col({
          title: "Schnitt",
          title_key: "average",
          field: `week${week}_avg`,
          width: "70px",
          decimal_places: 1,
        }),
      ]),
    );
  }
  const data = list.map((row) => {
    const out: Record<string, unknown> = {
      pos: asNum(row.rank ?? row.pos),
      team: asStr(row.team),
      season_points: asNum(row.points ?? row.season_points),
      season_score: asNum(row.pins ?? row.season_score),
      season_avg: asNum(row.average ?? row.season_avg),
    };
    const hist = asRecord(row.weeks);
    for (const week of weekNums) {
      const cell = asRecord(hist[String(week)] ?? hist[week]);
      out[`week${week}_points`] = asNum(cell.points);
      out[`week${week}_score`] = asNum(cell.pins);
      out[`week${week}_avg`] = asNum(cell.average);
    }
    return out;
  });
  return table(columns, data);
}

export function seriesToTeamSeries(
  series: Record<string, Array<number | null | undefined>> | undefined,
  options?: { accumulate?: boolean; rankSumSort?: boolean },
): TeamSeriesPayload {
  const data: Record<string, number[]> = {};
  const accumulated: Record<string, number[]> = {};
  const totals: Record<string, number> = {};
  for (const [team, values] of Object.entries(series ?? {})) {
    const nums = values.map((v) => (v == null || !Number.isFinite(Number(v)) ? 0 : Number(v)));
    data[team] = nums;
    const running: number[] = [];
    let sum = 0;
    for (const n of nums) {
      sum += n;
      running.push(sum);
    }
    accumulated[team] = running;
    totals[team] = sum;
  }
  const names = Object.keys(data);
  const sorted_by_total = [...names].sort((a, b) => totals[b] - totals[a] || a.localeCompare(b));
  if (options?.rankSumSort) {
    sorted_by_total.sort((a, b) => totals[b] - totals[a] || a.localeCompare(b));
  }
  return {
    data,
    data_accumulated: options?.accumulate ? accumulated : undefined,
    sorted_by_total,
    sorted_by_best: [...sorted_by_total].reverse(),
  };
}

export function seriesBundleFromV1(raw: unknown): {
  points: TeamSeriesPayload;
  positions: TeamSeriesPayload;
  averages: TeamSeriesPayload & { sorted_by_average?: string[] };
} {
  const rec = asRecord(raw);
  const points = seriesToTeamSeries(asRecord(rec.points) as Record<string, number[]>, {
    accumulate: true,
  });
  const positions = seriesToTeamSeries(asRecord(rec.positions) as Record<string, number[]>, {
    rankSumSort: true,
  });
  const averages = seriesToTeamSeries(asRecord(rec.averages) as Record<string, number[]>);
  const avgTotals: Record<string, number> = {};
  for (const [team, values] of Object.entries(averages.data)) {
    const valid = values.filter((n) => n != null && n !== 0);
    avgTotals[team] = valid.length ? valid.reduce((a, b) => a + b, 0) / valid.length : 0;
  }
  return {
    points,
    positions,
    averages: {
      ...averages,
      sorted_by_average: Object.keys(averages.data).sort(
        (a, b) => avgTotals[b] - avgTotals[a] || a.localeCompare(b),
      ),
    },
  };
}

export function timetableFromV1(raw: unknown): TableData {
  const rec = asRecord(raw);
  const weeks = asList(rec.weeks).map(asRecord);
  return table(
    [
      group("", [
        col({
          field: "week",
          title: "Spieltag",
          title_key: "week",
          align: "center",
          decimal_places: 0,
        }),
        col({ field: "date", title: "Datum", title_key: "date", align: "center" }),
        col({ field: "location", title: "Ort", title_key: "location", align: "left" }),
        col({ field: "status", title: "Status", title_key: "status", align: "center" }),
      ]),
    ],
    weeks.map((row) => ({
      week: asNum(row.week),
      date: asStr(row.date),
      location: asStr(row.location),
      status: asStr(row.status),
    })),
  );
}

export function individualAveragesTableFromV1(rows: unknown, team?: string | null): TableData {
  let list = asList(rows).map(asRecord);
  if (team) list = list.filter((row) => asStr(row.team) === team);
  return table(
    [
      group("", [
        col({
          title: "Spieler",
          title_key: "player",
          field: "player",
          width: "160px",
          align: "left",
        }),
        col({
          title: "Mannschaft",
          title_key: "team",
          field: "team",
          width: "160px",
          align: "left",
        }),
        col({
          title: "Spiele",
          title_key: "games",
          field: "games",
          width: "70px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Pins",
          title_key: "total_points",
          field: "total_points",
          width: "80px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Schnitt",
          title_key: "average",
          field: "average",
          width: "80px",
          align: "center",
          decimal_places: 1,
        }),
        col({
          title: "High Game",
          title_key: "high_game",
          field: "high_game",
          width: "80px",
          align: "center",
          decimal_places: 0,
        }),
      ]),
    ],
    list.map((row) => ({
      player: asStr(row.player),
      player_id: asStr(row.player_id),
      team: asStr(row.team),
      games: asNum(row.games),
      total_points: asNum(row.pins ?? row.total_points),
      average: asNum(row.average),
      high_game: asNum(row.high_game),
    })),
  );
}

export function compareTableFromV1(raw: unknown): TableData {
  const rec = asRecord(raw);
  const cells = asList(rec.cells).map(asRecord);
  const byPair = new Map<string, Dict>();
  const teams = new Set<string>();
  for (const cell of cells) {
    const team = asStr(cell.team);
    const opponent = asStr(cell.opponent);
    if (!team || !opponent) continue;
    teams.add(team);
    teams.add(opponent);
    byPair.set(`${team}\t${opponent}`, cell);
  }
  const ranked = asList(rec.teams).map(asStr).filter(Boolean);
  const ordered = [
    ...ranked.filter((name) => teams.has(name)),
    ...[...teams].filter((name) => !ranked.includes(name)).sort((a, b) => a.localeCompare(b)),
  ];
  const columns: ColumnGroup[] = [
    group(
      "Gegner →",
      [
        col({ title: "#", field: "pos", width: "50px", align: "center" }),
        col({
          title: "Mannschaft ↓",
          title_key: "team",
          field: "team",
          width: "160px",
          align: "left",
        }),
      ],
      { frozen: "left" },
    ),
    group("Schnitt", [
      col({
        title: "Pins",
        title_key: "score",
        field: "avg_score",
        width: "70px",
        align: "center",
      }),
      col({
        title: "Punkte",
        title_key: "points",
        field: "avg_points",
        width: "70px",
        align: "center",
      }),
    ]),
  ];
  for (const team of ordered) {
    columns.push(
      group(team, [
        col({
          title: "Pins",
          title_key: "score",
          field: `${team}_score`,
          width: "70px",
          align: "center",
        }),
        col({
          title: "Punkte",
          title_key: "points",
          field: `${team}_points`,
          width: "70px",
          align: "center",
        }),
      ]),
    );
  }
  const scores: number[] = [];
  const points: number[] = [];
  const matchups: Record<string, Record<string, { week: number }>> = {};
  const data = ordered.map((team, pos) => {
    const row: Record<string, unknown> = { pos: pos + 1, team };
    const playedScores: number[] = [];
    const playedPoints: number[] = [];
    for (const opponent of ordered) {
      if (team === opponent) {
        row[`${opponent}_score`] = "";
        row[`${opponent}_points`] = "";
        continue;
      }
      const cell = byPair.get(`${team}\t${opponent}`);
      const score = asNum(cell?.avg_pins);
      const pts = asNum(cell?.avg_points);
      row[`${opponent}_score`] = score ?? "";
      row[`${opponent}_points`] = pts ?? "";
      if (score != null) {
        playedScores.push(score);
        scores.push(score);
      }
      if (pts != null) {
        playedPoints.push(pts);
        points.push(pts);
      }
      const week = asNum(cell?.week);
      if (week != null) {
        (matchups[team] ??= {})[opponent] = { week };
      }
    }
    row.avg_score = playedScores.length
      ? Math.round((playedScores.reduce((a, b) => a + b, 0) / playedScores.length) * 10) / 10
      : "";
    row.avg_points = playedPoints.length
      ? Math.round((playedPoints.reduce((a, b) => a + b, 0) / playedPoints.length) * 10) / 10
      : "";
    return row;
  });
  return table(columns, data, {
    title: "Mannschaft vs. Mannschaft",
    metadata: {
      score_range: scores.length
        ? { min: Math.min(...scores), max: Math.max(...scores) }
        : undefined,
      points_range: points.length
        ? { min: Math.min(...points), max: Math.max(...points) }
        : undefined,
      week: asNum(rec.week),
      matchups,
    },
  });
}

export function gameOverviewTableFromV1(
  games: unknown,
  standings: unknown,
  round: string | number | null,
): TableData {
  const roundN = asNum(round);
  const ranks = new Map<string, number>();
  for (const row of asList(standings).map(asRecord)) {
    const team = asStr(row.team);
    const rank = asNum(row.rank ?? row.pos);
    if (team && rank != null) ranks.set(team, rank);
  }
  const ofRound = asList(games)
    .map(asRecord)
    .filter((row) => roundN == null || asNum(row.round) === roundN);
  const byTeam = new Map<string, Dict>();
  for (const row of ofRound) byTeam.set(asStr(row.team), row);
  const seen = new Set<string>();
  const data: Array<Record<string, unknown>> = [];
  for (const row of ofRound) {
    const team = asStr(row.team);
    const opponent = asStr(row.opponent);
    const key = [team, opponent].sort().join("\t");
    if (!team || seen.has(key)) continue;
    seen.add(key);
    const opp = byTeam.get(opponent) ?? {};
    data.push({
      team_position: ranks.get(team) ?? "",
      team_name: team,
      team_pins: asNum(row.team_pins),
      team_points: asNum(row.team_points),
      opponent_points: asNum(opp.team_points),
      opponent_pins: asNum(opp.team_pins),
      opponent_position: ranks.get(opponent) ?? "",
      opponent_name: opponent,
    });
  }
  return table(
    [
      group(
        "Mannschaft",
        [
          col({
            title: "Platz",
            title_key: "position",
            field: "team_position",
            width: "50px",
            align: "center",
            decimal_places: 0,
          }),
          col({
            title: "Mannschaft",
            title_key: "team",
            field: "team_name",
            width: "160px",
            align: "left",
          }),
          col({
            title: "Pins",
            title_key: "pins",
            field: "team_pins",
            width: "70px",
            align: "center",
            decimal_places: 0,
          }),
          col({
            title: "Punkte",
            title_key: "points",
            field: "team_points",
            width: "70px",
            align: "center",
            decimal_places: 0,
          }),
        ],
        { frozen: "left" },
      ),
      group("Gegner", [
        col({
          title: "Punkte",
          title_key: "points",
          field: "opponent_points",
          width: "70px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Pins",
          title_key: "pins",
          field: "opponent_pins",
          width: "70px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Platz",
          title_key: "position",
          field: "opponent_position",
          width: "50px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Gegner",
          title_key: "opponent",
          field: "opponent_name",
          width: "160px",
          align: "left",
        }),
      ]),
    ],
    data,
  );
}

export function classicDetailsTableFromV1(details: unknown): TableData {
  const rec = asRecord(details);
  const players = asList(rec.players).map(asRecord);
  const rounds = new Set<number>();
  for (const player of players) {
    for (const game of asList(player.games).map(asRecord)) {
      const n = asNum(game.round);
      if (n != null) rounds.add(n);
    }
  }
  const weekRounds = [...rounds].sort((a, b) => a - b);
  const columns: ColumnGroup[] = [
    group(
      "Spieler",
      [
        col({
          title: "Pos",
          title_key: "position",
          field: "position",
          width: "50px",
          align: "center",
          decimal_places: 0,
        }),
        col({ title: "Name", title_key: "name", field: "name", width: "160px", align: "left" }),
      ],
      { frozen: "left" },
    ),
  ];
  for (const rnd of weekRounds) {
    const opponent = players
      .map((p) =>
        asList(p.games)
          .map(asRecord)
          .find((g) => asNum(g.round) === rnd),
      )
      .find(Boolean);
    columns.push(
      group(asStr(asRecord(opponent).opponent) || `Spiel ${rnd}`, [
        col({
          title: "Pins",
          title_key: "pins",
          field: `game${rnd}_score`,
          width: "70px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Punkte",
          title_key: "points",
          field: `game${rnd}_points`,
          width: "70px",
          align: "center",
          decimal_places: 0,
        }),
      ]),
    );
  }
  columns.push(
    group("Gesamt", [
      col({
        title: "Punkte",
        title_key: "points",
        field: "total_points",
        width: "70px",
        align: "center",
        decimal_places: 0,
      }),
      col({
        title: "Pins",
        title_key: "score",
        field: "total_score",
        width: "70px",
        align: "center",
        decimal_places: 0,
      }),
      col({
        title: "Schnitt",
        title_key: "avg",
        field: "average",
        width: "70px",
        align: "center",
        decimal_places: 1,
      }),
    ]),
  );
  const data = players.map((player) => {
    const row: Record<string, unknown> = {
      position: displayPos(player.position),
      name: asStr(player.player),
      total_points: asNum(player.total_points),
      total_score: asNum(player.total_score),
      average: asNum(player.average),
    };
    for (const game of asList(player.games).map(asRecord)) {
      const rnd = asNum(game.round);
      if (rnd == null) continue;
      row[`game${rnd}_score`] = asNum(game.score);
      row[`game${rnd}_points`] = asNum(game.points);
    }
    return row;
  });
  return table(columns, data);
}

export function individualDetailsTableFromV1(details: unknown): TableData {
  const rec = asRecord(details);
  const players = asList(rec.players).map(asRecord);
  const rounds = asList(rec.rounds).map(asRecord);
  const columns: ColumnGroup[] = [
    group("Spiel", [
      col({
        title: "Gegner",
        title_key: "opponent",
        field: "opponent",
        width: "160px",
        align: "left",
      }),
      col({
        title: "Punkte gesamt",
        title_key: "total_points",
        field: "team_total_points",
        width: "80px",
        align: "center",
        decimal_places: 0,
      }),
    ]),
    group(asStr(rec.team), [
      col({
        title: "Pins",
        title_key: "pins",
        field: "team_score",
        width: "70px",
        align: "center",
        decimal_places: 0,
      }),
      col({
        title: "Punkte",
        title_key: "points",
        field: "team_points",
        width: "70px",
        align: "center",
        decimal_places: 0,
      }),
    ]),
  ];
  for (const player of players) {
    const token = fieldToken(playerKey(player) || asStr(player.player));
    columns.push(
      group(asStr(player.player), [
        col({
          title: "Pos",
          title_key: "position",
          field: `${token}_pos`,
          width: "50px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Pins",
          title_key: "score",
          field: `${token}_score`,
          width: "70px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Punkte",
          title_key: "points",
          field: `${token}_points`,
          width: "70px",
          align: "center",
          decimal_places: 0,
        }),
      ]),
    );
  }
  const data = rounds.map((round) => {
    const row: Record<string, unknown> = {
      opponent: asStr(round.opponent),
      team_score: asNum(round.team_score),
      team_points: asNum(round.team_points),
      team_total_points: asNum(round.team_points),
    };
    const cells = asList(round.players).map(asRecord);
    players.forEach((player, idx) => {
      const token = fieldToken(playerKey(player) || asStr(player.player));
      const cell = cells[idx] ?? {};
      row[`${token}_pos`] = displayPos(cell.position);
      row[`${token}_score`] = asNum(cell.score);
      row[`${token}_points`] = asNum(cell.points);
    });
    return row;
  });
  return table(columns, data);
}

export function h2hDetailsTableFromV1(details: unknown): TableData {
  const rec = asRecord(details);
  const own = asList(rec.own_players).map(asRecord);
  const opp = asList(rec.opp_players).map(asRecord);
  const rounds = asList(rec.rounds).map(asRecord);
  const columns: ColumnGroup[] = [
    group("Spielinfo", [
      col({
        title: "Runde",
        title_key: "round",
        field: "round_number",
        width: "60px",
        align: "center",
        decimal_places: 0,
      }),
      col({
        title: "Gegner",
        title_key: "opponent",
        field: "opponent_name",
        width: "160px",
        align: "left",
      }),
    ]),
  ];
  const addPlayers = (list: Dict[], prefix: string) => {
    for (const player of list) {
      const token = fieldToken(asStr(player.player));
      columns.push(
        group(asStr(player.player), [
          col({
            title: "Pos",
            title_key: "position",
            field: `${prefix}${token}_pos`,
            width: "50px",
            align: "center",
            decimal_places: 0,
          }),
          col({
            title: "Pins",
            title_key: "score",
            field: `${prefix}${token}_score`,
            width: "70px",
            align: "center",
            decimal_places: 0,
          }),
          col({
            title: "Punkte",
            title_key: "points",
            field: `${prefix}${token}_points`,
            width: "70px",
            align: "center",
            decimal_places: 0,
          }),
        ]),
      );
    }
  };
  addPlayers(own, "own_");
  addPlayers(opp, "opp_");
  columns.push(
    group("Mannschaft", [
      col({
        title: "Pins",
        title_key: "score",
        field: "team_score",
        width: "70px",
        align: "center",
        decimal_places: 0,
      }),
      col({
        title: "Punkte",
        title_key: "points",
        field: "team_points",
        width: "70px",
        align: "center",
        decimal_places: 0,
      }),
    ]),
  );
  const data = rounds.map((round) => {
    const row: Record<string, unknown> = {
      round_number: asNum(round.round),
      opponent_name: asStr(round.opponent),
      team_score: asNum(round.team_score),
      team_points: asNum(round.team_points),
    };
    const fill = (list: Dict[], cells: Dict[], prefix: string) => {
      list.forEach((player, idx) => {
        const token = fieldToken(asStr(player.player));
        const cell = cells[idx] ?? {};
        row[`${prefix}${token}_pos`] = displayPos(cell.position);
        row[`${prefix}${token}_score`] = asNum(cell.score);
        row[`${prefix}${token}_points`] = asNum(cell.points);
      });
    };
    fill(own, asList(round.own).map(asRecord), "own_");
    fill(opp, asList(round.opp).map(asRecord), "opp_");
    return row;
  });
  return table(columns, data);
}

export function teamDetailsTableFromV1(
  details: unknown,
  view: "classic" | "individual" | "headToHead",
): TableData {
  const rec = asRecord(details);
  const kind = asStr(rec.view);
  if (view === "individual" || kind === "individual") return individualDetailsTableFromV1(details);
  if (view === "headToHead" || kind === "h2h") return h2hDetailsTableFromV1(details);
  return classicDetailsTableFromV1(details);
}

export function gameTeamDetailsTableFromV1(details: unknown): TableData {
  const rec = asRecord(details);
  const players = asList(rec.players).map(asRecord);
  const data = players.map((row) => ({
    player_name: asStr(row.player),
    player_pins: asNum(row.pins),
    points: asNum(row.points),
    opponent_points: asNum(row.opponent_points),
    opponent_pins: asNum(row.opponent_pins),
    opponent_player_name: asStr(row.opponent_player),
  }));
  const totals = data.reduce(
    (acc, row) => {
      acc.player_pins += Number(row.player_pins ?? 0);
      acc.points += Number(row.points ?? 0);
      acc.opponent_points += Number(row.opponent_points ?? 0);
      acc.opponent_pins += Number(row.opponent_pins ?? 0);
      return acc;
    },
    { player_pins: 0, points: 0, opponent_points: 0, opponent_pins: 0 },
  );
  data.push({
    player_name: "Total",
    player_pins: totals.player_pins,
    points: totals.points,
    opponent_points: totals.opponent_points,
    opponent_pins: totals.opponent_pins,
    opponent_player_name: "",
  });
  return table(
    [
      group(
        asStr(rec.team),
        [
          col({
            title: "Spieler",
            title_key: "player",
            field: "player_name",
            width: "140px",
            align: "left",
          }),
          col({
            title: "Pins",
            title_key: "pins",
            field: "player_pins",
            width: "70px",
            align: "center",
            decimal_places: 0,
          }),
          col({
            title: "Punkte",
            title_key: "points",
            field: "points",
            width: "70px",
            align: "center",
            decimal_places: 0,
          }),
        ],
        { frozen: "left" },
      ),
      group(asStr(rec.opponent), [
        col({
          title: "Punkte",
          title_key: "points",
          field: "opponent_points",
          width: "70px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Pins",
          title_key: "pins",
          field: "opponent_pins",
          width: "70px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Spieler",
          title_key: "player",
          field: "opponent_player_name",
          width: "140px",
          align: "left",
        }),
      ]),
    ],
    data,
    {
      row_metadata: data.map((row) =>
        row.player_name === "Total" ? { styling: { fontWeight: "bold" } } : {},
      ),
    },
  );
}

function weekCount(series: Dict): number {
  const data = asRecord(series.data);
  const first = Object.values(data)[0];
  return Array.isArray(first) ? first.length : asList(series.weeks).length;
}

export function teamAnalysisFromV1(raw: unknown): TeamAnalysis {
  const rec = asRecord(raw);
  return {
    team: asStr(rec.team),
    performance_data: asRecord(rec.performance_data) as TeamAnalysis["performance_data"],
    win_percentage_data: asRecord(rec.win_percentage_data) as TeamAnalysis["win_percentage_data"],
    weeks: asList(rec.weeks) as Array<string | number>,
    player_order_by_average: asList(rec.player_order_by_average).map(asStr),
  };
}

export function teamPerformanceTableFromV1(raw: unknown): TableData {
  const rec = asRecord(raw);
  const analysis = teamAnalysisFromV1(rec);
  const perf = asRecord(analysis.performance_data);
  const data = asRecord(perf.data) as Record<string, Array<number | null>>;
  const totals = asRecord(perf.total) as Record<string, number>;
  const averages = asRecord(perf.average) as Record<string, number>;
  const counts = asRecord(perf.counts) as Record<string, number>;
  const team = analysis.team;
  const weeks = weekCount(perf);
  const columns: ColumnGroup[] = [
    group("Spieler", [
      col({ title: "#", field: "pos", width: "50px", align: "center", decimal_places: 0 }),
      col({
        title: "Spieler",
        title_key: "player",
        field: "player_name",
        width: "150px",
        align: "left",
      }),
    ]),
  ];
  const weekCols: ColumnDef[] = [];
  for (let i = 0; i < weeks; i += 1) {
    weekCols.push(
      col({
        title: String(i + 1),
        field: `week_${i + 1}`,
        width: "80px",
        align: "center",
        decimal_places: 1,
      }),
    );
  }
  if (weekCols.length) columns.push(group("Wochenschnitt", weekCols));
  columns.push(
    group("Gesamt", [
      col({
        title: "Pins",
        title_key: "ui.team_performance.total_score",
        field: "total_score",
        width: "80px",
        align: "center",
        decimal_places: 0,
      }),
      col({
        title: "Spiele",
        title_key: "games",
        field: "total_games",
        width: "70px",
        align: "center",
        decimal_places: 0,
      }),
      col({
        title: "Schnitt",
        title_key: "ui.team_performance.avg_per_game",
        field: "avg_per_game",
        width: "80px",
        align: "center",
        decimal_places: 1,
      }),
    ]),
  );
  const order = (analysis.player_order_by_average ?? []).filter(
    (name) => name in data && name !== team,
  );
  const names = [
    ...order,
    ...Object.keys(data).filter((name) => name !== team && !order.includes(name)),
  ];
  if (team in data) names.push(team);
  const rows = names.map((name, idx) => {
    const values = data[name] ?? [];
    const row: Record<string, unknown> = {
      pos: idx + 1,
      player_name: name,
      total_score: totals[name] ?? 0,
      total_games: counts[name] ?? 0,
      avg_per_game: averages[name] ?? 0,
    };
    for (let i = 0; i < weeks; i += 1) row[`week_${i + 1}`] = values[i] ?? null;
    return row;
  });
  return table(columns, rows, {
    row_metadata: rows.map((row) =>
      row.player_name === team ? { styling: { fontWeight: "bold" } } : {},
    ),
  });
}

export function teamWinPercentageTableFromV1(raw: unknown): TableData {
  const rec = asRecord(raw);
  const analysis = teamAnalysisFromV1(rec);
  const win = asRecord(analysis.win_percentage_data);
  const nested = "data" in win ? asRecord(win.data) : win;
  const data = nested as Record<string, Array<number | null>>;
  const totals = asRecord(win.total) as Record<string, number>;
  const averages = asRecord(win.average) as Record<string, number>;
  const counts = asRecord(win.counts) as Record<string, number>;
  const team = analysis.team;
  const weeks = weekCount(win.data ? win : { data: nested });
  const columns: ColumnGroup[] = [
    group("Spieler", [
      col({ title: "#", field: "pos", width: "50px", align: "center", decimal_places: 0 }),
      col({
        title: "Spieler",
        title_key: "ui.win_percentage.player",
        field: "player_name",
        width: "150px",
        align: "left",
      }),
    ]),
  ];
  const weekCols: ColumnDef[] = [];
  for (let i = 0; i < weeks; i += 1) {
    weekCols.push(
      col({
        title: String(i + 1),
        field: `week_${i + 1}`,
        width: "70px",
        align: "center",
        decimal_places: 1,
      }),
    );
  }
  if (weekCols.length) columns.push(group("Wöchentlich", weekCols));
  columns.push(
    group("Gesamt", [
      col({
        title: "Siege",
        title_key: "ui.win_percentage.total_wins",
        field: "total_wins",
        width: "70px",
        align: "center",
        decimal_places: 0,
      }),
      col({
        title: "Spiele",
        title_key: "ui.win_percentage.total_matches",
        field: "total_matches",
        width: "70px",
        align: "center",
        decimal_places: 0,
      }),
      col({
        title: "Siegquote",
        title_key: "ui.win_percentage.win_percentage",
        field: "win_percentage",
        width: "80px",
        align: "center",
        decimal_places: 1,
      }),
    ]),
  );
  const order = (analysis.player_order_by_average ?? []).filter(
    (name) => name in data && name !== team,
  );
  const names = [
    ...order,
    ...Object.keys(data).filter((name) => name !== team && !order.includes(name)),
  ];
  if (team in data) names.push(team);
  const rows = names.map((name, idx) => {
    const values = data[name] ?? [];
    const row: Record<string, unknown> = {
      pos: idx + 1,
      player_name: name,
      total_wins: totals[name] ?? 0,
      total_matches: counts[name] ?? 0,
      win_percentage: averages[name] ?? 0,
    };
    for (let i = 0; i < weeks; i += 1) row[`week_${i + 1}`] = values[i] ?? null;
    return row;
  });
  return table(columns, rows, {
    row_metadata: rows.map((row) =>
      row.player_name === team ? { styling: { fontWeight: "bold" } } : {},
    ),
  });
}

export function seasonStandingsFromV1(raw: unknown): SeasonLeagueStandings {
  const rec = asRecord(raw);
  return {
    leagues: asList(rec.leagues).map((item) => {
      const row = asRecord(item);
      return {
        league: asStr(row.league),
        league_long: asStr(row.league_long || row.league),
        week: asNum(row.week) ?? "",
        standings: standingsTableFromV1(row.standings),
        honor_scores: honorFromV1(row.honor_scores),
      };
    }),
  };
}

export function recordsChartFromV1(
  rows: unknown,
  valueKey: "average" | "points",
  title: string,
  yAxis: string,
): LeagueHistoryChart {
  const list = asList(rows).map(asRecord);
  const seasons = list.map((row) => asStr(row.season)).filter(Boolean);
  return {
    data: { [title]: list.map((row) => asNum(row[valueKey]) ?? 0) },
    seasons,
    labels: seasons,
    title,
    y_axis_title: yAxis,
  };
}

export function recordsTableFromV1(
  rows: unknown,
  kind: "top_team" | "top_individual" | "record_games" | "record_team",
): TableData {
  const list = asList(rows).map(asRecord);
  if (kind === "top_team") {
    return table(
      [
        group("", [
          col({ title: "Mannschaft", title_key: "team", field: "team", align: "left" }),
          col({
            title: "Schnitt",
            title_key: "average",
            field: "average",
            align: "center",
            decimal_places: 1,
          }),
          col({ title: "Saison", title_key: "season", field: "season", align: "center" }),
          col({ title: "Liga", title_key: "league", field: "league", align: "left" }),
        ]),
      ],
      list.map((row) => ({
        team: asStr(row.team),
        average: asNum(row.average),
        season: asStr(row.season),
        league: asStr(row.league),
      })),
      { default_sort: { field: "average", dir: "desc" } },
    );
  }
  if (kind === "top_individual") {
    return table(
      [
        group("", [
          col({ title: "Spieler", title_key: "player", field: "player", align: "left" }),
          col({
            title: "Schnitt",
            title_key: "average",
            field: "average",
            align: "center",
            decimal_places: 1,
          }),
          col({ title: "Saison", title_key: "season", field: "season", align: "center" }),
          col({ title: "Liga", title_key: "league", field: "league", align: "left" }),
          col({ title: "Mannschaft", title_key: "team", field: "team", align: "left" }),
        ]),
      ],
      list.map((row) => ({
        player: asStr(row.player),
        average: asNum(row.average),
        season: asStr(row.season),
        league: asStr(row.league),
        team: asStr(row.team),
      })),
      { default_sort: { field: "average", dir: "desc" } },
    );
  }
  if (kind === "record_team") {
    return table(
      [
        group("", [
          col({ title: "Mannschaft", title_key: "team", field: "team", align: "left" }),
          col({
            title: "Pins",
            title_key: "score",
            field: "score",
            align: "center",
            decimal_places: 0,
          }),
          col({ title: "Saison", title_key: "season", field: "season", align: "center" }),
          col({ title: "Liga", title_key: "league", field: "league", align: "left" }),
          col({
            title: "Spieltag",
            title_key: "week",
            field: "week",
            align: "center",
            decimal_places: 0,
          }),
        ]),
      ],
      list.map((row) => ({
        team: asStr(row.team),
        score: asNum(row.score),
        season: asStr(row.season),
        league: asStr(row.league),
        week: asNum(row.week),
      })),
      { default_sort: { field: "score", dir: "desc" } },
    );
  }
  return table(
    [
      group("", [
        col({ title: "Spieler", title_key: "player", field: "player", align: "left" }),
        col({
          title: "Pins",
          title_key: "score",
          field: "score",
          align: "center",
          decimal_places: 0,
        }),
        col({ title: "Saison", title_key: "season", field: "season", align: "center" }),
        col({ title: "Liga", title_key: "league", field: "league", align: "left" }),
        col({ title: "Mannschaft", title_key: "team", field: "team", align: "left" }),
        col({
          title: "Spieltag",
          title_key: "week",
          field: "week",
          align: "center",
          decimal_places: 0,
        }),
      ]),
    ],
    list.map((row) => ({
      player: asStr(row.player),
      score: asNum(row.score),
      season: asStr(row.season),
      league: asStr(row.league),
      team: asStr(row.team),
      week: asNum(row.week),
    })),
    { default_sort: { field: "score", dir: "desc" } },
  );
}

export async function loadMeta(
  params: { season?: string | null; league?: string | null; week?: string | number | null } = {},
) {
  return catalogFromV1(await fetchV1("/api/v1/meta", params));
}

export async function loadSeasonStandings(season: string) {
  return seasonStandingsFromV1(await fetchV1("/api/v1/seasons/standings", { season }));
}

export async function loadLeagueStandings(season: string, league: string) {
  return asRecord(await fetchV1("/api/v1/leagues/standings", { season, league, view: "history" }));
}

export async function loadTimetable(season: string, league: string) {
  return timetableFromV1(await fetchV1("/api/v1/leagues/timetable", { season, league }));
}

export async function loadMatchday(
  season: string,
  league: string,
  week: string | number,
  extra: Record<string, string | number | undefined | null> = {},
) {
  return asRecord(await fetchV1(`/api/v1/leagues/matchdays/${week}`, { season, league, ...extra }));
}

export async function loadCompare(season: string, league: string, week?: string | null) {
  return asRecord(
    await fetchV1("/api/v1/leagues/compare", { season, league, week: week || undefined }),
  );
}

export async function loadRecords(league: string) {
  return asRecord(await fetchV1("/api/v1/leagues/records", { league }));
}

export async function loadTeamInLeague(season: string, league: string, team: string) {
  return asRecord(await fetchV1("/api/v1/leagues/team", { season, league, team }));
}

export function detailsViewParam(view: "classic" | "individual" | "headToHead"): string {
  if (view === "individual") return "individual";
  if (view === "headToHead") return "h2h";
  return "classic";
}
