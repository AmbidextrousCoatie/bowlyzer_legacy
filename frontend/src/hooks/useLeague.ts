import { useQueries, useQuery } from "@tanstack/react-query";
import { loadClubMatrix } from "../lib/clubMatrixV1";
import { loadClubLegends } from "../lib/clubLegendsV1";
import { loadClubPlayerResults } from "../lib/clubPlayerResultsV1";
import { loadClubRankings } from "../lib/clubRankingsV1";
import { loadOddities, loadWeekMatrix } from "../lib/diagnosisV1";
import type { ClubMatrixSeasonCell } from "../lib/clubMatrixCell";
import type { TableData } from "../lib/datatable/types";
import {
  compareTableFromV1,
  detailsViewParam,
  gameOverviewTableFromV1,
  gameTeamDetailsTableFromV1,
  honorFromV1,
  individualAveragesTableFromV1,
  loadCompare,
  loadLeagueStandings,
  loadMatchday,
  loadMeta,
  loadRecords,
  loadSeasonStandings,
  loadTeamInLeague,
  loadTimetable,
  recordsChartFromV1,
  recordsTableFromV1,
  seriesBundleFromV1,
  standingsTableFromV1,
  teamAnalysisFromV1,
  teamDetailsTableFromV1,
  teamPerformanceTableFromV1,
  teamWinPercentageTableFromV1,
} from "../lib/leagueV1";
import { V1_QUERY_KEY } from "../lib/v1";

export type Season = string;

export type LeagueOption = {
  short_name: string;
  long_name: string;
  value: string;
};

export type HonorScoreEntry = {
  player?: string;
  player_name?: string;
  team?: string;
  team_name?: string;
  name?: string;
  score?: number | string;
  total_score?: number | string;
  average?: number | string;
  value?: number | string;
  /** When present, honor link targets game/round detail instead of team week only. */
  round?: number | string;
  game?: number | string;
};

export type HonorScores = {
  individual_scores?: HonorScoreEntry[];
  team_scores?: HonorScoreEntry[];
  individual_averages?: HonorScoreEntry[];
  team_averages?: HonorScoreEntry[];
};

export type SeasonLeagueStandings = {
  leagues: Array<{
    league: string;
    league_long?: string;
    week: number | string;
    standings: TableData;
    honor_scores?: HonorScores;
  }>;
};

export { pickLatestSeason } from "../lib/leagueSeason";

export function useAvailableSeasons() {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "meta", "seasons"],
    queryFn: () => loadMeta(),
    select: (data) => data.seasons,
  });
}

export function useAvailableLeagues(season: string | null) {
  const allSeasons = !season;
  return useQuery({
    queryKey: [V1_QUERY_KEY, "meta", "leagues", allSeasons ? "all" : season],
    queryFn: () => loadMeta({ season }),
    select: (data) => data.leagues,
  });
}

export function useSeasonLeagueStandings(season: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "seasons", "standings", season],
    queryFn: () => loadSeasonStandings(season!),
    enabled: !!season,
  });
}

export function useLeagueHistory(season: string | null, league: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "standings", season, league],
    queryFn: () => loadLeagueStandings(season!, league!),
    select: (doc) => standingsTableFromV1(doc.standings, { history: true }),
    enabled: !!season && !!league,
  });
}

export function useSeasonTimetable(season: string | null, league: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "timetable", season, league],
    queryFn: () => loadTimetable(season!, league!),
    enabled: !!season && !!league,
  });
}

/** Parallel Termine fetches for every league in the season (or Mein Club) view. */
export function useSeasonTimetables(season: string | null, leagues: string[], enabled = true) {
  return useQueries({
    queries: leagues.map((league) => ({
      queryKey: [V1_QUERY_KEY, "leagues", "timetable", season, league] as const,
      queryFn: () => loadTimetable(season!, league),
      enabled: enabled && !!season && !!league,
    })),
  });
}

export function useIndividualAverages(
  season: string | null,
  league: string | null,
  week?: string | null,
  team?: string | null,
) {
  const matchday = Boolean(week);
  return useQuery({
    queryKey: matchday
      ? [V1_QUERY_KEY, "leagues", "matchday", season, league, week]
      : [V1_QUERY_KEY, "leagues", "standings", season, league],
    queryFn: () =>
      matchday ? loadMatchday(season!, league!, week!) : loadLeagueStandings(season!, league!),
    select: (doc) => individualAveragesTableFromV1(doc.players, team),
    enabled: !!season && !!league,
  });
}

export function useTeamVsTeamComparison(
  season: string | null,
  league: string | null,
  week?: string | null,
) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "compare", season, league, week ?? ""],
    queryFn: async () => compareTableFromV1(await loadCompare(season!, league!, week)),
    enabled: !!season && !!league,
  });
}

export type TeamSeriesPayload = {
  data: Record<string, number[]>;
  data_accumulated?: Record<string, number[]>;
  sorted_by_total?: string[];
  sorted_by_best?: string[];
};

export function useTeamPoints(season: string | null, league: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "standings", season, league],
    queryFn: () => loadLeagueStandings(season!, league!),
    select: (doc) => seriesBundleFromV1(doc.series).points,
    enabled: !!season && !!league,
  });
}

export function useTeamPositions(season: string | null, league: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "standings", season, league],
    queryFn: () => loadLeagueStandings(season!, league!),
    select: (doc) => seriesBundleFromV1(doc.series).positions,
    enabled: !!season && !!league,
  });
}

export function useTeamAverages(season: string | null, league: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "standings", season, league],
    queryFn: () => loadLeagueStandings(season!, league!),
    select: (doc) => seriesBundleFromV1(doc.series).averages,
    enabled: !!season && !!league,
  });
}

// ───── Filter-rail dimensions ────────────────────────────────────────────

export function useAvailableWeeks(season: string | null, league: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "meta", "league", season, league],
    queryFn: () => loadMeta({ season, league }),
    select: (data) => data.weeks,
    enabled: !!season && !!league,
  });
}

export function useAvailableTeams(season: string | null, league: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "meta", "league", season, league],
    queryFn: () => loadMeta({ season, league }),
    select: (data) => data.teams,
    enabled: !!season && !!league,
  });
}

export function useAvailableRounds(
  season: string | null,
  league: string | null,
  week: string | null,
) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "meta", "league", season, league, week],
    queryFn: () => loadMeta({ season, league, week }),
    select: (data) => data.rounds,
    enabled: !!season && !!league && !!week,
  });
}

// ───── Matchday ──────────────────────────────────────────────────────────

export function useLeagueWeekTable(
  season: string | null,
  league: string | null,
  week: string | null,
) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "matchday", season, league, week],
    queryFn: () => loadMatchday(season!, league!, week!),
    select: (doc) => standingsTableFromV1(doc.table),
    enabled: !!season && !!league && !!week,
  });
}

export function useHonorScores(season: string | null, league: string | null, week: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "matchday", season, league, week],
    queryFn: () => loadMatchday(season!, league!, week!),
    select: (doc) => honorFromV1(doc.honor_scores),
    enabled: !!season && !!league && !!week,
  });
}

// ───── Team details (3 view modes) ───────────────────────────────────────

export type TeamDetailsView = "classic" | "individual" | "headToHead";

export function useTeamWeekDetails(
  season: string | null,
  league: string | null,
  week: string | null,
  team: string | null,
  view: TeamDetailsView,
) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "matchday", season, league, week, team, view],
    queryFn: () =>
      loadMatchday(season!, league!, week!, { team: team!, view: detailsViewParam(view) }),
    select: (doc) => teamDetailsTableFromV1(doc.details, view),
    enabled: !!season && !!league && !!week && !!team,
  });
}

// ───── Team performance ──────────────────────────────────────────────────

export type TeamAnalysis = {
  team: string;
  performance_data?: {
    data: Record<string, number[]>;
    weeks?: string[] | number[];
  };
  win_percentage_data?: Record<string, number[]>;
  weeks?: Array<string | number>;
  player_order_by_average?: string[];
};

export function useTeamAnalysis(season: string | null, league: string | null, team: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "team", season, league, team],
    queryFn: () => loadTeamInLeague(season!, league!, team!),
    select: (doc) => teamAnalysisFromV1(doc),
    enabled: !!season && !!league && !!team,
  });
}

export function useTeamPerformanceTable(
  season: string | null,
  league: string | null,
  team: string | null,
) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "team", season, league, team],
    queryFn: () => loadTeamInLeague(season!, league!, team!),
    select: (doc) => teamPerformanceTableFromV1(doc),
    enabled: !!season && !!league && !!team,
  });
}

export function useTeamWinPercentageTable(
  season: string | null,
  league: string | null,
  team: string | null,
) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "team", season, league, team],
    queryFn: () => loadTeamInLeague(season!, league!, team!),
    select: (doc) => teamWinPercentageTableFromV1(doc),
    enabled: !!season && !!league && !!team,
  });
}

// ───── Round-level (game) blocks ─────────────────────────────────────────

export function useGameOverview(
  season: string | null,
  league: string | null,
  week: string | null,
  round: string | null,
) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "matchday", season, league, week],
    queryFn: () => loadMatchday(season!, league!, week!),
    select: (doc) => gameOverviewTableFromV1(doc.games, doc.table, round),
    enabled: !!season && !!league && !!week && !!round,
  });
}

export type ClubMatrixRow = {
  team_number: string;
  seasons: Record<string, ClubMatrixSeasonCell>;
};

export type ClubMatrixPayload = {
  clubs: string[];
  selected_club: string;
  only_unnumbered: boolean;
  matrix: {
    club: string;
    seasons: string[];
    rows: ClubMatrixRow[];
  };
  league_long_names: Record<string, string>;
};

export type WeekMatrixCell = {
  label: string;
  status: "ok" | "warn" | "bad" | "critical" | "";
  missing_weeks?: number[];
  available_weeks?: number[];
  /** Expected matchdays for this league/season (Bayernliga=6, else team count). */
  expected_weeks?: number;
  team_count?: number;
  /** Short league id for deep links when row label merges BL/BZOL. */
  league_id?: string;
};

export type WeekMatrixPayload = {
  matrix: {
    seasons: string[];
    rows: Array<{ league: string; seasons: Record<string, WeekMatrixCell> }>;
    expected_weeks_rule?: string;
  };
  league_long_names?: Record<string, string>;
};

const DIAGNOSIS_LIST_STALE_MS = 10 * 60 * 1000;

export type ClubLegendEntry = {
  player_id: string;
  player_name: string;
  value: number;
  games?: number;
  average?: number;
  season?: string;
  teams?: string[];
  leagues?: string[];
};

export type ClubLegendsPayload = {
  club: string;
  most_seasons: ClubLegendEntry[];
  most_games: ClubLegendEntry[];
  highest_average: ClubLegendEntry[];
  best_seasons: ClubLegendEntry[];
  most_teams_represented: ClubLegendEntry[];
  most_leagues_seen: ClubLegendEntry[];
};

export function normalizeClubLegendsPayload(
  raw: Partial<ClubLegendsPayload> | null | undefined,
): ClubLegendsPayload {
  return {
    club: raw?.club ?? "",
    most_seasons: raw?.most_seasons ?? [],
    most_games: raw?.most_games ?? [],
    highest_average: raw?.highest_average ?? [],
    best_seasons: raw?.best_seasons ?? [],
    most_teams_represented: raw?.most_teams_represented ?? [],
    most_leagues_seen: raw?.most_leagues_seen ?? [],
  };
}

export type ClubPlayerResultsPayload = {
  club: string;
  table: TableData;
};

function scopedClubSeason(season?: string | null): string | undefined {
  const value = (season ?? "").trim();
  if (!value || value === "all" || value === "latest") return undefined;
  return value;
}

export function useClubPlayerResults(
  club: string | null,
  options?: { enabled?: boolean; season?: string | null },
) {
  const enabled = options?.enabled ?? true;
  const season = scopedClubSeason(options?.season);
  return useQuery({
    queryKey: [V1_QUERY_KEY, "clubs", "players", club ?? "", season ?? "all"],
    queryFn: () => loadClubPlayerResults(club ?? "", season),
    staleTime: DIAGNOSIS_LIST_STALE_MS,
    enabled: enabled && Boolean(club),
  });
}

export type ClubRankingEntry = {
  club: string;
  value: number;
  team?: string;
  season?: string;
  league?: string;
  week?: string;
  round?: string;
  match_total?: number;
};

export type ClubRankingsPayload = {
  top_n: number;
  highest_total_pinfall: ClubRankingEntry[];
  most_members: ClubRankingEntry[];
  highest_weekly_team_average: ClubRankingEntry[];
  highest_team_game_average: ClubRankingEntry[];
  most_tournament_wins: ClubRankingEntry[];
  most_league_wins: ClubRankingEntry[];
};

export function normalizeClubRankingsPayload(
  raw: Partial<ClubRankingsPayload> | null | undefined,
): ClubRankingsPayload {
  return {
    top_n: raw?.top_n ?? 5,
    highest_total_pinfall: raw?.highest_total_pinfall ?? [],
    most_members: raw?.most_members ?? [],
    highest_weekly_team_average: raw?.highest_weekly_team_average ?? [],
    highest_team_game_average: raw?.highest_team_game_average ?? [],
    most_tournament_wins: raw?.most_tournament_wins ?? [],
    most_league_wins: raw?.most_league_wins ?? [],
  };
}

export function useClubRankings(options?: { enabled?: boolean }) {
  const enabled = options?.enabled ?? true;
  return useQuery({
    queryKey: [V1_QUERY_KEY, "clubs", "rankings"],
    queryFn: () => loadClubRankings(),
    select: normalizeClubRankingsPayload,
    staleTime: DIAGNOSIS_LIST_STALE_MS,
    enabled,
  });
}

export function useClubLegends(
  club: string | null,
  options?: { enabled?: boolean; season?: string | null },
) {
  const enabled = options?.enabled ?? true;
  const season = scopedClubSeason(options?.season);
  return useQuery({
    queryKey: [V1_QUERY_KEY, "clubs", "legends", club ?? "", season ?? "all"],
    queryFn: () => loadClubLegends(club ?? "", season),
    staleTime: DIAGNOSIS_LIST_STALE_MS,
    enabled: enabled && Boolean(club),
  });
}

export function useClubMatrix(
  club: string | null,
  onlyUnnumbered: boolean,
  options?: { enabled?: boolean },
) {
  const enabled = options?.enabled ?? true;
  return useQuery({
    queryKey: [V1_QUERY_KEY, "clubs", "matrix", club ?? "", onlyUnnumbered],
    queryFn: () => loadClubMatrix(club, onlyUnnumbered),
    staleTime: DIAGNOSIS_LIST_STALE_MS,
    enabled,
  });
}

/** One matrix fetch per club (parallel) for diagnosis multi-club view. */
export function useClubMatrices(selectedClubs: string[], onlyUnnumbered: boolean) {
  return useQueries({
    queries: selectedClubs.map((club) => ({
      queryKey: [V1_QUERY_KEY, "clubs", "matrix", club, onlyUnnumbered],
      queryFn: () => loadClubMatrix(club, onlyUnnumbered),
      staleTime: DIAGNOSIS_LIST_STALE_MS,
      enabled: Boolean(club),
    })),
  });
}

export function useWeekMatrix() {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "diagnosis", "week-matrix"],
    queryFn: () => loadWeekMatrix(),
    staleTime: DIAGNOSIS_LIST_STALE_MS,
  });
}

export type DataOddityType =
  | "unnumbered_team"
  | "low_score"
  | "incomplete_row"
  | "incomplete_squad"
  | "over_roster"
  | "named_missing_side";

export type DataOddity = {
  id: string;
  type: DataOddityType;
  severity: "info" | "warn" | "bad" | "critical";
  message: string;
  context: Record<string, string | number | null | undefined>;
  deep_link?: { path: string; params: Record<string, string> };
};

export type DataOdditiesPayload = {
  oddities: DataOddity[];
  summary: { total: number; by_type: Partial<Record<DataOddityType, number>> };
  limit: number;
  truncated: boolean;
  league_long_names?: Record<string, string>;
};

export function useDataOddities(types: DataOddityType[]) {
  const typesKey = types.slice().sort().join(",");
  return useQuery({
    queryKey: [V1_QUERY_KEY, "diagnosis", "oddities", typesKey],
    queryFn: () => loadOddities(types),
    staleTime: DIAGNOSIS_LIST_STALE_MS,
  });
}

export function useGameTeamDetails(
  season: string | null,
  league: string | null,
  week: string | null,
  team: string | null,
  round: string | null,
) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "matchday", season, league, week, team, "game", round],
    queryFn: () => loadMatchday(season!, league!, week!, { team: team!, round: round! }),
    select: (doc) => gameTeamDetailsTableFromV1(doc.game_details),
    enabled: !!season && !!league && !!week && !!team && !!round,
  });
}

export type LeagueHistoryChart = {
  data: Record<string, number[]>;
  seasons: string[];
  labels: string[];
  title?: string;
  y_axis_title?: string;
};

export function useLeagueAveragesHistory(league: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "records", league],
    queryFn: () => loadRecords(league!),
    select: (doc) =>
      recordsChartFromV1(doc.averages_history, "average", "League Average", "Average Score"),
    enabled: !!league,
  });
}

export function usePointsToWinHistory(league: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "records", league],
    queryFn: () => loadRecords(league!),
    select: (doc) => recordsChartFromV1(doc.points_to_win, "points", "Points to Win", "Points"),
    enabled: !!league,
  });
}

export function useTopTeamPerformances(league: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "records", league],
    queryFn: () => loadRecords(league!),
    select: (doc) => recordsTableFromV1(doc.top_team, "top_team"),
    enabled: !!league,
  });
}

export function useTopIndividualPerformances(league: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "records", league],
    queryFn: () => loadRecords(league!),
    select: (doc) => recordsTableFromV1(doc.top_individual, "top_individual"),
    enabled: !!league,
  });
}

export function useRecordGames(league: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "records", league],
    queryFn: () => loadRecords(league!),
    select: (doc) => recordsTableFromV1(doc.record_games, "record_games"),
    enabled: !!league,
  });
}

export function useRecordIndividualGames(league: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "records", league],
    queryFn: () => loadRecords(league!),
    select: (doc) => recordsTableFromV1(doc.record_individual ?? doc.record_games, "record_games"),
    enabled: !!league,
  });
}

export function useRecordTeamGames(league: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "leagues", "records", league],
    queryFn: () => loadRecords(league!),
    select: (doc) => recordsTableFromV1(doc.record_team, "record_team"),
    enabled: !!league,
  });
}
