import { useQueries, useQuery } from "@tanstack/react-query";
import { buildUrl, fetchJson } from "../lib/api";
import type { ClubMatrixSeasonCell } from "../lib/clubMatrixCell";
import type { TableData } from "../lib/datatable/types";

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
    queryKey: ["league", "seasons"],
    queryFn: () => fetchJson<Season[]>(buildUrl("/league/get_available_seasons")),
  });
}

export function useAvailableLeagues(season: string | null) {
  const allSeasons = !season;
  return useQuery({
    queryKey: ["league", "leagues", allSeasons ? "all" : season],
    queryFn: () =>
      fetchJson<LeagueOption[]>(
        allSeasons
          ? buildUrl("/league/get_available_leagues")
          : buildUrl("/league/get_available_leagues", { season }),
      ),
  });
}

export function useSeasonLeagueStandings(season: string | null) {
  return useQuery({
    queryKey: ["league", "season-standings", season],
    queryFn: () =>
      fetchJson<SeasonLeagueStandings>(buildUrl("/league/get_season_league_standings", { season })),
    enabled: !!season,
  });
}

export function useLeagueHistory(season: string | null, league: string | null) {
  return useQuery({
    queryKey: ["league", "history", season, league],
    queryFn: () => fetchJson<TableData>(buildUrl("/league/get_league_history", { season, league })),
    enabled: !!season && !!league,
  });
}

export function useSeasonTimetable(season: string | null, league: string | null) {
  return useQuery({
    queryKey: ["league", "timetable", season, league],
    queryFn: () =>
      fetchJson<TableData>(buildUrl("/league/get_season_timetable", { season, league })),
    enabled: !!season && !!league,
  });
}

export function useIndividualAverages(
  season: string | null,
  league: string | null,
  week?: string | null,
  team?: string | null,
) {
  return useQuery({
    queryKey: ["league", "individual-averages", season, league, week, team],
    queryFn: () =>
      fetchJson<TableData>(
        buildUrl("/league/get_individual_averages", {
          season,
          league,
          week: week ?? undefined,
          team: team ?? undefined,
        }),
      ),
    enabled: !!season && !!league,
  });
}

export function useTeamVsTeamComparison(
  season: string | null,
  league: string | null,
  week?: string | null,
) {
  return useQuery({
    queryKey: ["league", "team-vs-team", season, league, week],
    queryFn: () =>
      fetchJson<TableData>(
        buildUrl("/league/get_team_vs_team_comparison", {
          season,
          league,
          week: week ?? undefined,
        }),
      ),
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
    queryKey: ["league", "team-points", season, league],
    queryFn: () =>
      fetchJson<TeamSeriesPayload>(buildUrl("/league/get_team_points", { season, league })),
    enabled: !!season && !!league,
  });
}

export function useTeamPositions(season: string | null, league: string | null) {
  return useQuery({
    queryKey: ["league", "team-positions", season, league],
    queryFn: () =>
      fetchJson<TeamSeriesPayload>(buildUrl("/league/get_team_positions", { season, league })),
    enabled: !!season && !!league,
  });
}

export function useTeamAverages(season: string | null, league: string | null) {
  return useQuery({
    queryKey: ["league", "team-averages", season, league],
    queryFn: () =>
      fetchJson<TeamSeriesPayload & { sorted_by_average?: string[] }>(
        buildUrl("/league/get_team_averages", { season, league }),
      ),
    enabled: !!season && !!league,
  });
}

// ───── Filter-rail dimensions ────────────────────────────────────────────

export function useAvailableWeeks(season: string | null, league: string | null) {
  return useQuery({
    queryKey: ["league", "weeks", season, league],
    queryFn: () => fetchJson<number[]>(buildUrl("/league/get_available_weeks", { season, league })),
    enabled: !!season && !!league,
  });
}

export function useAvailableTeams(season: string | null, league: string | null) {
  return useQuery({
    queryKey: ["league", "teams", season, league],
    queryFn: () => fetchJson<string[]>(buildUrl("/league/get_available_teams", { season, league })),
    enabled: !!season && !!league,
  });
}

export function useAvailableRounds(
  season: string | null,
  league: string | null,
  week: string | null,
) {
  return useQuery({
    queryKey: ["league", "rounds", season, league, week],
    queryFn: () =>
      fetchJson<number[]>(buildUrl("/league/get_available_rounds", { season, league, week })),
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
    queryKey: ["league", "week-table", season, league, week],
    queryFn: () =>
      fetchJson<TableData>(buildUrl("/league/get_league_week_table", { season, league, week })),
    enabled: !!season && !!league && !!week,
  });
}

export function useHonorScores(season: string | null, league: string | null, week: string | null) {
  return useQuery({
    queryKey: ["league", "honor-scores", season, league, week],
    queryFn: () =>
      fetchJson<HonorScores>(buildUrl("/league/get_honor_scores", { season, league, week })),
    enabled: !!season && !!league && !!week,
  });
}

// ───── Team details (3 view modes) ───────────────────────────────────────

export type TeamDetailsView = "classic" | "individual" | "headToHead";

const TEAM_DETAILS_ENDPOINTS: Record<TeamDetailsView, string> = {
  classic: "/league/get_team_week_details_table",
  individual: "/league/get_team_individual_scores_table",
  headToHead: "/league/get_team_week_head_to_head_table",
};

export function useTeamWeekDetails(
  season: string | null,
  league: string | null,
  week: string | null,
  team: string | null,
  view: TeamDetailsView,
) {
  return useQuery({
    queryKey: ["league", "team-week-details", season, league, week, team, view],
    queryFn: () =>
      fetchJson<TableData>(buildUrl(TEAM_DETAILS_ENDPOINTS[view], { season, league, week, team })),
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
    queryKey: ["league", "team-analysis", season, league, team],
    queryFn: () =>
      fetchJson<TeamAnalysis>(buildUrl("/league/get_team_analysis", { season, league, team })),
    enabled: !!season && !!league && !!team,
  });
}

export function useTeamPerformanceTable(
  season: string | null,
  league: string | null,
  team: string | null,
) {
  return useQuery({
    queryKey: ["league", "team-performance-table", season, league, team],
    queryFn: () =>
      fetchJson<TableData>(
        buildUrl("/league/get_team_performance_table", { season, league, team }),
      ),
    enabled: !!season && !!league && !!team,
  });
}

export function useTeamWinPercentageTable(
  season: string | null,
  league: string | null,
  team: string | null,
) {
  return useQuery({
    queryKey: ["league", "team-win-percentage-table", season, league, team],
    queryFn: () =>
      fetchJson<TableData>(
        buildUrl("/league/get_team_win_percentage_table", {
          season,
          league,
          team,
        }),
      ),
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
    queryKey: ["league", "game-overview", season, league, week, round],
    queryFn: () =>
      fetchJson<TableData>(buildUrl("/league/get_game_overview", { season, league, week, round })),
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

export function useClubPlayerResults(club: string | null, options?: { enabled?: boolean }) {
  const database =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("database")
      : null;
  const enabled = options?.enabled ?? true;
  return useQuery({
    queryKey: ["league", "club-player-results", database ?? "", club ?? ""],
    queryFn: () =>
      fetchJson<ClubPlayerResultsPayload>(
        buildUrl("/league/get_club_player_results", { club: club || undefined }),
      ),
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
  const database =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("database")
      : null;
  const enabled = options?.enabled ?? true;
  return useQuery({
    queryKey: ["league", "club-rankings", database ?? ""],
    queryFn: () => fetchJson<ClubRankingsPayload>(buildUrl("/league/get_club_rankings")),
    select: normalizeClubRankingsPayload,
    staleTime: DIAGNOSIS_LIST_STALE_MS,
    enabled,
  });
}

export function useClubLegends(club: string | null, options?: { enabled?: boolean }) {
  const database =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("database")
      : null;
  const enabled = options?.enabled ?? true;
  return useQuery({
    queryKey: ["league", "club-legends", database ?? "", club ?? ""],
    queryFn: () =>
      fetchJson<ClubLegendsPayload>(
        buildUrl("/league/get_club_legends", { club: club || undefined }),
      ),
    select: normalizeClubLegendsPayload,
    staleTime: DIAGNOSIS_LIST_STALE_MS,
    enabled: enabled && Boolean(club),
  });
}

export function useClubMatrix(
  club: string | null,
  onlyUnnumbered: boolean,
  options?: { enabled?: boolean },
) {
  const database =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("database")
      : null;
  const enabled = options?.enabled ?? true;
  return useQuery({
    queryKey: ["league", "club-matrix", database ?? "", club ?? "", onlyUnnumbered],
    queryFn: () =>
      fetchJson<ClubMatrixPayload>(
        buildUrl("/league/get_club_matrix", {
          club: club || undefined,
          only_unnumbered: onlyUnnumbered ? 1 : undefined,
        }),
      ),
    staleTime: DIAGNOSIS_LIST_STALE_MS,
    enabled,
  });
}

/** One matrix fetch per club (parallel) for diagnosis multi-club view. */
export function useClubMatrices(selectedClubs: string[], onlyUnnumbered: boolean) {
  const database =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("database")
      : null;
  return useQueries({
    queries: selectedClubs.map((club) => ({
      queryKey: ["league", "club-matrix", database ?? "", club, onlyUnnumbered],
      queryFn: () =>
        fetchJson<ClubMatrixPayload>(
          buildUrl("/league/get_club_matrix", {
            club,
            only_unnumbered: onlyUnnumbered ? 1 : undefined,
          }),
        ),
      staleTime: DIAGNOSIS_LIST_STALE_MS,
      enabled: Boolean(club),
    })),
  });
}

export function useWeekMatrix() {
  const database =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("database")
      : null;
  return useQuery({
    queryKey: ["league", "week-matrix", database ?? ""],
    queryFn: () => fetchJson<WeekMatrixPayload>(buildUrl("/league/get_week_matrix")),
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
  const database =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("database")
      : null;
  const typesKey = types.slice().sort().join(",");
  return useQuery({
    queryKey: ["league", "data-oddities", database ?? "", typesKey],
    queryFn: () =>
      fetchJson<DataOdditiesPayload>(
        buildUrl("/league/get_data_oddities", {
          types: types.length > 0 ? types.join(",") : undefined,
        }),
      ),
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
    queryKey: ["league", "game-team-details", season, league, week, team, round],
    queryFn: () =>
      fetchJson<TableData>(
        buildUrl("/league/get_game_team_details", {
          season,
          league,
          week,
          team,
          round,
        }),
      ),
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

function useLeagueAggregationQuery<T>(
  endpoint: string,
  league: string | null,
  extraParams?: Record<string, string>,
) {
  return useQuery({
    queryKey: ["league", endpoint, league, extraParams?.debug ?? ""],
    queryFn: () =>
      fetchJson<T>(
        buildUrl(`/league/${endpoint}`, { league: league!, ...extraParams }),
      ),
    enabled: !!league,
  });
}

export function useLeagueAveragesHistory(league: string | null) {
  return useLeagueAggregationQuery<LeagueHistoryChart>(
    "get_league_averages_history",
    league,
    { debug: "false" },
  );
}

export function usePointsToWinHistory(league: string | null) {
  return useLeagueAggregationQuery<LeagueHistoryChart>(
    "get_points_to_win_history",
    league,
    { debug: "false" },
  );
}

export function useTopTeamPerformances(league: string | null) {
  return useLeagueAggregationQuery<TableData>("get_top_team_performances", league);
}

export function useTopIndividualPerformances(league: string | null) {
  return useLeagueAggregationQuery<TableData>("get_top_individual_performances", league);
}

export function useRecordGames(league: string | null) {
  return useLeagueAggregationQuery<TableData>("get_record_games", league);
}

export function useRecordIndividualGames(league: string | null) {
  return useLeagueAggregationQuery<TableData>("get_record_individual_games", league);
}

export function useRecordTeamGames(league: string | null) {
  return useLeagueAggregationQuery<TableData>("get_record_team_games", league);
}
