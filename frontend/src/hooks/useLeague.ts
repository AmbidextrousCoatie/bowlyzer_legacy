import { useQuery } from "@tanstack/react-query";
import { buildUrl, fetchJson } from "../lib/api";
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

/** Picks the newest season label (matches legacy league-stats-app.js). */
export function pickLatestSeason(seasons: string[]): string | null {
  if (seasons.length === 0) return null;
  return seasons.reduce((a, b) => (String(a) > String(b) ? a : b));
}

export function useAvailableSeasons() {
  return useQuery({
    queryKey: ["league", "seasons"],
    queryFn: () => fetchJson<Season[]>("/league/get_available_seasons"),
  });
}

export function useAvailableLeagues(season: string | null) {
  return useQuery({
    queryKey: ["league", "leagues", season],
    queryFn: () => fetchJson<LeagueOption[]>(buildUrl("/league/get_available_leagues", { season })),
    enabled: !!season,
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
