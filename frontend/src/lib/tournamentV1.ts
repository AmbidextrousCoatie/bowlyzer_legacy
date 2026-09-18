import type { PlayerSearchEntry } from "../hooks/usePlayer";
import type {
  TournamentBestEfforts,
  TournamentFieldProgress,
  TournamentFormatInfo,
  TournamentHandicapFormatInfo,
  TournamentPlayerResultRow,
  TournamentPlayerSection,
  TournamentPodiumsPayload,
  TournamentProgressSeries,
  TournamentRound,
  TournamentSection,
  TournamentSummaryCard,
} from "../hooks/useTournament";
import type { ColumnDef, ColumnGroup, TableData } from "./datatable/types";
import { normalizeTournamentGroupName } from "./tournamentGroupName";
import { fetchV1 } from "./v1";

type Dict = Record<string, unknown>;

const GAME_HEATMAP = {
  min: 130,
  max: 270,
  high_band_min: 271,
  high_band_max: 299,
  perfect_score: 300,
};

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

function hasClub(rows: Dict[]): boolean {
  return rows.some((row) => asStr(row.club));
}

function gameFields(rows: Dict[]): number[] {
  const nums = new Set<number>();
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      const match = /^game_(\d+)$/.exec(key);
      if (match) nums.add(Number(match[1]));
    }
  }
  return [...nums].sort((a, b) => a - b);
}

function roundFields(rows: Dict[]): number[] {
  const nums = new Set<number>();
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      const match = /^round_(\d+)$/.exec(key);
      if (match) nums.add(Number(match[1]));
    }
  }
  return [...nums].sort((a, b) => a - b);
}

export function leaderboardTableFromV1(
  raw: unknown,
  extra: { rounds?: TournamentRound[]; useNet?: boolean; koBracketFormat?: string } = {},
): TableData {
  const rows = asList(raw).map(asRecord);
  const useNet =
    extra.useNet ??
    rows.some(
      (row) => row.total_net != null || row.avg_net != null || row.handicap_display != null,
    );
  const singleRound = rows.some((row) => row.round_score != null);
  const includeClub = hasClub(rows);
  const playerCols: ColumnDef[] = [
    col({
      title: "#",
      field: "rank",
      width: "60px",
      align: "center",
      decimal_places: 0,
      frozen: "left",
    }),
    col({
      title: "Spieler",
      title_key: "player",
      field: "player",
      width: "132px",
      align: "left",
      frozen: "left",
    }),
  ];
  if (useNet) {
    playerCols.push(
      col({
        title: "HCP",
        title_key: "ui.tournament.handicap_col_short",
        field: "handicap_display",
        width: "92px",
        align: "center",
        tooltip: "Handicap pins per game",
      }),
    );
  }
  if (includeClub) {
    playerCols.push(
      col({
        title: "Club",
        title_key: "ui.player.club",
        field: "club",
        width: "220px",
        align: "center",
      }),
    );
  }
  const data = rows.map((row) => ({
    ...row,
    player: asStr(row.player || row.player_name),
  }));

  if (singleRound) {
    const stageCols = useNet
      ? [
          col({
            title: "Pins",
            title_key: "ui.tournament.col_pins_scratch",
            field: "round_score",
            width: "110px",
            align: "center",
            decimal_places: 0,
          }),
          col({
            title: "Ø",
            title_key: "ui.tournament.col_avg_scratch",
            field: "avg_score",
            width: "100px",
            align: "center",
            decimal_places: 1,
          }),
          col({
            title: "Netto",
            title_key: "ui.tournament.col_pins_net",
            field: "round_net",
            width: "110px",
            align: "center",
            decimal_places: 0,
          }),
          col({
            title: "Ø Netto",
            title_key: "ui.tournament.col_avg_net",
            field: "avg_round_net",
            width: "100px",
            align: "center",
            decimal_places: 1,
          }),
        ]
      : [
          col({
            title: "Pins",
            title_key: "score",
            field: "round_score",
            width: "110px",
            align: "center",
            decimal_places: 0,
          }),
          col({
            title: "Ø",
            title_key: "average",
            field: "avg_score",
            width: "100px",
            align: "center",
            decimal_places: 1,
          }),
        ];
    const totalCols = useNet
      ? [
          col({
            title: "Pins",
            title_key: "ui.tournament.col_pins_scratch",
            field: "total_score",
            width: "110px",
            align: "center",
            decimal_places: 0,
          }),
          col({
            title: "Ø",
            title_key: "ui.tournament.col_avg_scratch",
            field: "total_avg",
            width: "110px",
            align: "center",
            decimal_places: 1,
          }),
          col({
            title: "Netto",
            title_key: "ui.tournament.col_pins_net",
            field: "total_net",
            width: "110px",
            align: "center",
            decimal_places: 0,
          }),
          col({
            title: "Ø Netto",
            title_key: "ui.tournament.col_avg_net",
            field: "total_avg_net",
            width: "110px",
            align: "center",
            decimal_places: 1,
          }),
        ]
      : [
          col({
            title: "Pins",
            title_key: "score",
            field: "total_score",
            width: "110px",
            align: "center",
            decimal_places: 0,
          }),
          col({
            title: "Ø",
            title_key: "average",
            field: "total_avg",
            width: "110px",
            align: "center",
            decimal_places: 1,
          }),
        ];
    return table(
      [
        group("Spieler", playerCols),
        group("Runde", stageCols),
        group("Gesamt", totalCols, { highlighted: true }),
      ],
      data,
      {
        title: "Leaderboard",
        default_sort: { field: useNet ? "total_net" : "total_score", dir: "desc" },
        metadata: useNet ? { leaderboard_mode: "single_round_net" } : {},
        config: { stripedColGroups: true, stickyHeader: true, striped: true },
      },
    );
  }

  const roundNums = roundFields(rows);
  const roundName = (rn: number) =>
    extra.rounds?.find((item) => Number(item.round_number) === rn)?.round_name || `Round ${rn}`;
  const scratchCols: ColumnDef[] = roundNums.map((rn) =>
    col({
      title: roundName(rn),
      field: `round_${rn}`,
      width: "90px",
      align: "center",
      decimal_places: 0,
    }),
  );
  scratchCols.push(
    col({
      title: "Total",
      title_key: "ui.tournament.lb_total_scratch",
      field: "total_score",
      width: "90px",
      align: "center",
      decimal_places: 0,
    }),
    col({
      title: "Ø",
      title_key: "table.header.average",
      field: "avg_scratch",
      width: "80px",
      align: "center",
      decimal_places: 1,
    }),
  );
  const columns: ColumnGroup[] = [group("Spieler", playerCols), group("Scratch", scratchCols)];
  if (useNet) {
    columns.push(
      group("Netto", [
        col({
          title: "Total",
          title_key: "ui.tournament.lb_total_net",
          field: "total_net",
          width: "90px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Ø",
          title_key: "table.header.average",
          field: "avg_net",
          width: "80px",
          align: "center",
          decimal_places: 1,
        }),
      ]),
    );
  }
  const stepladder = extra.koBracketFormat === "seeded_elim_stepladder";
  const metadata: Record<string, unknown> = {};
  if (useNet) metadata.leaderboard_mode = "scratch_net_handicap";
  if (stepladder) metadata.standings_order = "ko_then_average";
  if (extra.koBracketFormat) {
    metadata.initial_sort = [{ field: "rank", dir: "asc" }];
  }
  return table(columns, data, {
    title: "Leaderboard",
    default_sort: { field: "rank", dir: "asc" },
    metadata,
    config: { stripedColGroups: true, stickyHeader: true, striped: true },
  });
}

export function roundResultsTableFromV1(raw: unknown, extra: { useNet?: boolean } = {}): TableData {
  const rows = asList(raw).map(asRecord);
  const useNet =
    extra.useNet ?? rows.some((row) => row.stage_net != null || row.handicap_display != null);
  const includeClub = hasClub(rows);
  const games = gameFields(rows);
  const includeStage = new Set(rows.map((row) => asNum(row.round_number))).size > 1;
  const playerCols: ColumnDef[] = [
    col({
      title: "#",
      field: "overall_rank",
      width: "70px",
      align: "center",
      decimal_places: 0,
      frozen: "left",
    }),
    col({
      title: "Spieler",
      title_key: "player",
      field: "player",
      width: "132px",
      align: "left",
      frozen: "left",
    }),
  ];
  if (useNet) {
    playerCols.push(
      col({
        title: "HCP",
        title_key: "ui.tournament.handicap_col_short",
        field: "handicap_display",
        width: "92px",
        align: "center",
      }),
    );
  }
  if (includeClub) {
    playerCols.push(
      col({
        title: "Club",
        title_key: "ui.player.club",
        field: "club",
        width: "220px",
        align: "center",
      }),
    );
  }
  if (includeStage) {
    playerCols.push(
      col({
        title: "Runde",
        title_key: "ui.tournament.stage",
        field: "stage",
        width: "140px",
        align: "left",
      }),
    );
  }
  const gameCols = games.map((g) =>
    col({
      title: String(g + 1),
      field: `game_${g}`,
      width: "75px",
      align: "center",
      decimal_places: 0,
    }),
  );
  const stageCols = useNet
    ? [
        col({
          title: "Pins",
          title_key: "ui.tournament.col_pins_scratch",
          field: "stage_score",
          width: "110px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Ø",
          title_key: "ui.tournament.col_avg_scratch",
          field: "stage_avg",
          width: "100px",
          align: "center",
          decimal_places: 1,
        }),
        col({
          title: "Netto",
          title_key: "ui.tournament.col_pins_net",
          field: "stage_net",
          width: "110px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Ø Netto",
          title_key: "ui.tournament.col_avg_net",
          field: "stage_avg_net",
          width: "100px",
          align: "center",
          decimal_places: 1,
        }),
      ]
    : [
        col({
          title: "Pins",
          title_key: "score",
          field: "stage_score",
          width: "110px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Ø",
          title_key: "average",
          field: "avg_score",
          width: "100px",
          align: "center",
          decimal_places: 1,
        }),
      ];
  const totalCols = useNet
    ? [
        col({
          title: "Pins",
          title_key: "ui.tournament.col_pins_scratch",
          field: "total_score",
          width: "110px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Ø",
          title_key: "ui.tournament.col_avg_scratch",
          field: "total_avg",
          width: "100px",
          align: "center",
          decimal_places: 1,
        }),
        col({
          title: "Netto",
          title_key: "ui.tournament.col_pins_net",
          field: "overall_net",
          width: "110px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Ø Netto",
          title_key: "ui.tournament.col_avg_net",
          field: "overall_avg_net",
          width: "100px",
          align: "center",
          decimal_places: 1,
        }),
      ]
    : [
        col({
          title: "Pins",
          title_key: "score",
          field: "total_score",
          width: "110px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Ø",
          title_key: "average",
          field: "overall_avg",
          width: "100px",
          align: "center",
          decimal_places: 1,
        }),
      ];
  const data = rows.map((row) => ({
    ...row,
    player: asStr(row.player || row.player_name),
    stage: asStr(row.stage || row.round_name),
  }));
  return table(
    [
      group("Spieler", playerCols),
      group("Spiele", gameCols),
      group("Runde", stageCols),
      group("Gesamt", totalCols, { highlighted: true }),
    ],
    data,
    {
      title: "Round Results",
      metadata: { heatmap_ranges: { game_score: GAME_HEATMAP } },
      config: { stripedColGroups: true, stickyHeader: true },
    },
  );
}

export function playerRoundTableFromV1(raw: unknown, extra: { useNet?: boolean } = {}): TableData {
  const rows = asList(raw).map(asRecord);
  const useNet = extra.useNet ?? rows.some((row) => row.stage_net != null || row.round_hcp != null);
  const games = gameFields(rows);
  const stageCols: ColumnDef[] = [
    col({
      title: "Runde",
      title_key: "ui.tournament.stage",
      field: "stage",
      width: "140px",
      align: "left",
    }),
  ];
  const hcpCols = useNet
    ? [
        col({
          title: "HCP",
          title_key: "ui.tournament.handicap_per_game",
          field: "round_hcp",
          width: "92px",
          align: "center",
        }),
      ]
    : [];
  const gameCols = games.map((g) =>
    col({
      title: String(g + 1),
      field: `game_${g}`,
      width: "70px",
      align: "center",
      decimal_places: 0,
    }),
  );
  const stageStatCols = useNet
    ? [
        col({
          title: "Pins",
          title_key: "ui.tournament.col_pins_scratch",
          field: "stage_score",
          width: "110px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Ø",
          title_key: "ui.tournament.col_avg_scratch",
          field: "stage_avg",
          width: "100px",
          align: "center",
          decimal_places: 1,
        }),
        col({
          title: "Netto",
          title_key: "ui.tournament.col_pins_net",
          field: "stage_net",
          width: "110px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Ø Netto",
          title_key: "ui.tournament.col_avg_net",
          field: "stage_avg_net",
          width: "100px",
          align: "center",
          decimal_places: 1,
        }),
        col({
          title: "#",
          title_key: "ui.tournament.rank",
          field: "round_rank",
          width: "95px",
          align: "center",
          decimal_places: 0,
        }),
      ]
    : [
        col({
          title: "Pins",
          title_key: "score",
          field: "score_total",
          width: "105px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Ø",
          title_key: "average",
          field: "round_avg",
          width: "90px",
          align: "center",
          decimal_places: 1,
        }),
        col({
          title: "#",
          title_key: "ui.tournament.rank",
          field: "round_rank",
          width: "95px",
          align: "center",
          decimal_places: 0,
        }),
      ];
  const totalCols = useNet
    ? [
        col({
          title: "Pins",
          title_key: "ui.tournament.col_pins_scratch",
          field: "cum_score",
          width: "110px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Ø",
          title_key: "ui.tournament.col_avg_scratch",
          field: "cum_avg_sc",
          width: "100px",
          align: "center",
          decimal_places: 1,
        }),
        col({
          title: "Netto",
          title_key: "ui.tournament.col_pins_net",
          field: "overall_net",
          width: "110px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Ø Netto",
          title_key: "ui.tournament.col_avg_net",
          field: "overall_avg_net",
          width: "100px",
          align: "center",
          decimal_places: 1,
        }),
        col({
          title: "#",
          title_key: "ui.tournament.rank",
          field: "cum_rank",
          width: "90px",
          align: "center",
          decimal_places: 0,
        }),
      ]
    : [
        col({
          title: "Pins",
          title_key: "score",
          field: "cum_score",
          width: "95px",
          align: "center",
          decimal_places: 0,
        }),
        col({
          title: "Ø",
          title_key: "average",
          field: "cum_avg",
          width: "90px",
          align: "center",
          decimal_places: 1,
        }),
        col({
          title: "#",
          title_key: "ui.tournament.rank",
          field: "cum_rank",
          width: "90px",
          align: "center",
          decimal_places: 0,
        }),
      ];
  const groups: ColumnGroup[] = [group("Runde", stageCols, { frozen: "left" })];
  if (hcpCols.length) groups.push(group("", hcpCols));
  groups.push(group("Spiele", gameCols), group("Runde", stageStatCols), group("Gesamt", totalCols));
  return table(groups, rows, {
    title: "Tournament Progress",
    metadata: { heatmap_ranges: { game_score: GAME_HEATMAP } },
  });
}

export function formatFromV1(raw: unknown): TournamentFormatInfo {
  const rec = asRecord(raw);
  const handicap = asRecord(rec.handicap);
  const columns = asRecord(handicap.columns);
  const handicapInfo: TournamentHandicapFormatInfo = {
    used: Boolean(handicap.used),
    columns: {
      handicap: Boolean(columns.handicap),
      apriori_average: Boolean(columns.apriori_average),
      handicap_reference: Boolean(columns.handicap_reference),
    },
    pins: (handicap.pins as TournamentHandicapFormatInfo["pins"]) ?? null,
    a_priori_average:
      (handicap.a_priori_average as TournamentHandicapFormatInfo["a_priori_average"]) ?? null,
    handicap_reference:
      (handicap.handicap_reference as TournamentHandicapFormatInfo["handicap_reference"]) ?? null,
  };
  return {
    round_count: asNum(rec.round_count) ?? asList(rec.rounds).length,
    rounds: asList(rec.rounds).map((item) => {
      const row = asRecord(item);
      return {
        round_number: asNum(row.round_number) ?? 0,
        round_name: asStr(row.round_name),
        is_ko_finale_cluster: Boolean(row.is_ko_finale_cluster),
      };
    }),
    handicap: handicapInfo,
    ko_finale_round_number_in_data: asNum(rec.ko_finale_round_number_in_data),
    ko_bracket_format: asStr(rec.ko_bracket_format) || undefined,
    ko_decision_basis: asStr(rec.ko_decision_basis) || undefined,
    ko_finale_series: asStr(rec.ko_finale_series) || undefined,
    ko_finale_series_label_de: asStr(rec.ko_finale_series_label_de) || undefined,
    ko_finale_series_label_en: asStr(rec.ko_finale_series_label_en) || undefined,
    qualifying_cut_span:
      (rec.qualifying_cut_span as TournamentFormatInfo["qualifying_cut_span"]) ?? null,
    qualifying_cut_pair:
      (rec.qualifying_cut_pair as TournamentFormatInfo["qualifying_cut_pair"]) ?? null,
    qualifying_stages: asList(rec.qualifying_stages) as TournamentFormatInfo["qualifying_stages"],
    config: asRecord(rec.config),
  };
}

function fieldProgressFromV1(raw: unknown): TournamentFieldProgress {
  const rec = asRecord(raw);
  return {
    labels: asList(rec.labels).map(asStr),
    tournament_leader_avg_series: asList(rec.tournament_leader_avg_series) as Array<number | null>,
    tournament_lowest_avg_series: asList(rec.tournament_lowest_avg_series) as Array<number | null>,
    round_end_lines: asList(rec.round_end_lines) as Array<number | null>,
    cut_lines_avg: asList(rec.cut_lines_avg) as Array<number | null>,
    cut_lines_position: asList(rec.cut_lines_position) as Array<number | null>,
    cut_position_at_game: asList(rec.cut_position_at_game) as Array<number | null>,
    participant_count: asNum(rec.participant_count) ?? undefined,
  };
}

export function sectionFromV1(raw: unknown): TournamentSection {
  const rec = asRecord(raw);
  const rounds = asList(rec.rounds).map((item) => {
    const row = asRecord(item);
    return {
      round_number: asNum(row.round_number) ?? row.round_number,
      round_name: asStr(row.round_name),
      is_ko_finale_cluster: Boolean(row.is_ko_finale_cluster),
    };
  });
  const useNet = Boolean(rec.use_net);
  const koBracketFormat =
    asStr(asRecord(rec.format).ko_bracket_format) ||
    asStr(asRecord(rec.ko_bracket).ko_bracket_format);
  return {
    cards: asList(rec.cards) as TournamentSummaryCard[],
    leaderboard: leaderboardTableFromV1(rec.leaderboard, { rounds, useNet, koBracketFormat }),
    round_results: roundResultsTableFromV1(rec.round_results, { useNet }),
    rounds,
    best_efforts: asRecord(rec.best_efforts) as TournamentBestEfforts,
    field_progress: fieldProgressFromV1(rec.field_progress),
    ko_bracket: rec.ko_bracket ? (rec.ko_bracket as TournamentSection["ko_bracket"]) : undefined,
    is_ko_finale_round: Boolean(rec.is_ko_finale_round),
    ko_finale_round_number: asNum(rec.ko_finale_round_number),
  };
}

export function playerSectionFromV1(raw: unknown): TournamentPlayerSection {
  const rec = asRecord(raw);
  const useNet =
    Boolean(asRecord(rec.best_efforts).handicap_profile) ||
    asList(rec.round_table).some((row) => asRecord(row).stage_net != null);
  const progress = asRecord(rec.progress_series);
  return {
    player: asStr(rec.player),
    player_club: asStr(rec.player_club) || null,
    player_card_layout: asList(
      rec.player_card_layout,
    ) as TournamentPlayerSection["player_card_layout"],
    round_table: playerRoundTableFromV1(rec.round_table, { useNet }),
    best_efforts: asRecord(rec.best_efforts) as TournamentPlayerSection["best_efforts"],
    progress_series: {
      labels: asList(progress.labels).map(asStr),
      avg_series: asList(progress.avg_series) as TournamentProgressSeries["avg_series"],
      position_series: asList(
        progress.position_series,
      ) as TournamentProgressSeries["position_series"],
      game_score_series: asList(
        progress.game_score_series,
      ) as TournamentProgressSeries["game_score_series"],
      tournament_leader_avg_series: asList(
        progress.tournament_leader_avg_series,
      ) as TournamentProgressSeries["tournament_leader_avg_series"],
      round_end_lines: asList(
        progress.round_end_lines,
      ) as TournamentProgressSeries["round_end_lines"],
    },
    field_progress: fieldProgressFromV1(rec.field_progress),
    summary: asRecord(rec.summary) as TournamentPlayerSection["summary"],
    ko_bracket: rec.ko_bracket
      ? (rec.ko_bracket as TournamentPlayerSection["ko_bracket"])
      : undefined,
  };
}

export function podiumsFromV1(raw: unknown): TournamentPodiumsPayload {
  const rec = asRecord(raw);
  return {
    top_n: asNum(rec.top_n) ?? 3,
    podiums: asList(rec.podiums).map((item) => {
      const row = asRecord(item);
      const tournament = asStr(row.tournament || row.event);
      return {
        season: asStr(row.season),
        tournament,
        tournament_group: asStr(row.tournament_group) || normalizeTournamentGroupName(tournament),
        tournament_average: asNum(row.tournament_average),
        finishers: asList(row.finishers).map((fin) => {
          const f = asRecord(fin);
          return {
            rank: asNum(f.rank) ?? 0,
            rank_label: asStr(f.rank_label) || undefined,
            player: asStr(f.player || f.player_name),
            club: asStr(f.club) || null,
            average: asNum(f.average),
          };
        }),
      };
    }),
  };
}

export function playerResultsFromV1(raw: unknown): TournamentPlayerResultRow[] {
  const rec = asRecord(raw);
  const rows = Array.isArray(raw) ? raw : rec.results;
  return asList(rows).map((item) => {
    const row = asRecord(item);
    const tournament = asStr(row.tournament || row.event);
    return {
      season: asStr(row.season),
      tournament,
      tournament_group: asStr(row.tournament_group) || normalizeTournamentGroupName(tournament),
      position: asNum(row.position ?? row.rank),
      average: asNum(row.average),
      club: asStr(row.club) || null,
    };
  });
}

export function playersFromV1(raw: unknown): PlayerSearchEntry[] {
  const rec = asRecord(raw);
  const rows = Array.isArray(raw) ? raw : rec.players;
  return asList(rows)
    .map((item) => {
      const row = asRecord(item);
      return {
        id: asStr(row.id || row.player_id),
        name: asStr(row.name || row.player_name),
        aliases: asList(row.aliases).map(asStr).filter(Boolean),
      };
    })
    .filter((row) => row.name);
}

export async function loadTournamentCatalog(params: {
  season?: string | null;
  club?: string | null;
  event?: string | null;
}): Promise<{
  seasons: string[];
  events: string[];
  tournaments: Array<{ season: string; event: string }>;
}> {
  const raw = await fetchV1<Dict>("/api/v1/tournaments", {
    season: params.season || undefined,
    club: params.club || undefined,
    event: params.event || undefined,
    tournament: params.event || undefined,
  });
  const items = asList(raw.tournaments).map(asRecord);
  const events = asList(raw.events).map(asStr).filter(Boolean);
  const groups = events.length
    ? events
    : [
        ...new Set(
          items.map(
            (row) => asStr(row.tournament_group) || normalizeTournamentGroupName(asStr(row.event)),
          ),
        ),
      ].filter(Boolean);
  return {
    seasons: asList(raw.seasons).map(asStr).filter(Boolean),
    events: groups.sort((a, b) => a.localeCompare(b)),
    tournaments: items.map((row) => ({ season: asStr(row.season), event: asStr(row.event) })),
  };
}

export async function loadTournamentDocument(
  season: string,
  event: string,
  round?: string | null,
): Promise<Dict> {
  return fetchV1<Dict>("/api/v1/tournaments/section", {
    season,
    event,
    round: round || undefined,
    n: 5,
  });
}

export async function loadTournamentPodiums(params: {
  season?: string | null;
  event?: string | null;
  club?: string | null;
}): Promise<TournamentPodiumsPayload> {
  const raw = await fetchV1<Dict>("/api/v1/tournaments/podiums", {
    season: params.season || undefined,
    event: params.event || undefined,
    tournament: params.event || undefined,
    club: params.club || undefined,
    n: 3,
  });
  return podiumsFromV1(raw);
}

export async function loadTournamentPlayers(params: {
  season?: string | null;
  event?: string | null;
  round?: string | null;
}): Promise<PlayerSearchEntry[]> {
  const raw = await fetchV1<Dict>("/api/v1/tournaments/players", {
    season: params.season || undefined,
    event: params.event || undefined,
    tournament: params.event || undefined,
    round: params.round || undefined,
  });
  return playersFromV1(raw);
}

export async function loadPlayerTournaments(
  player: string,
  params: { season?: string | null; event?: string | null } = {},
): Promise<TournamentPlayerResultRow[]> {
  const raw = await fetchV1<Dict>("/api/v1/players/tournaments", {
    player,
    season: params.season || undefined,
    event: params.event || undefined,
    tournament: params.event || undefined,
  });
  return playerResultsFromV1(raw);
}

export async function loadTournamentPlayerSection(
  season: string,
  event: string,
  player: string,
): Promise<Dict> {
  return fetchV1<Dict>("/api/v1/tournaments/player", { season, event, tournament: event, player });
}
