import { useQuery } from "@tanstack/react-query";
import { buildUrl, fetchJson } from "../lib/api";

const TEAM_STALE_MS = 5 * 60_000;

/** Must match `useClubMatrix` — cache is keyed per `?database=` so sources do not bleed. */
export function teamQueryDatabase(): string {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get("database") ?? "";
}

export type TeamHistorySeason = {
  league_name: string;
  final_position: number;
  league_level: number;
  statistics?: {
    total_score?: number;
    total_points?: number;
    average_score?: number;
    games_played?: number;
    best_score?: number;
    worst_score?: number;
  };
};

export type TeamHistory = Record<string, TeamHistorySeason>;

export type LeagueComparisonSeason = {
  league_name: string;
  league_averages: {
    average_score?: number;
    average_points?: number;
    num_teams?: number;
  };
  team_performance: {
    team_average_score?: number;
    team_average_points?: number;
    vs_league_average?: number;
    performance_rank?: number;
  };
  performance_rank?: number;
  vs_league_average?: number;
};

export type LeagueComparison = Record<string, LeagueComparisonSeason>;

export type ClutchAnalysis = {
  total_games?: number;
  total_clutch_games?: number;
  total_clutch_wins?: number;
  total_clutch_losses?: number;
  clutch_percentage?: number;
  opponent_clutch?: Record<string, { wins: number; losses: number }>;
  error?: string;
};

export type ConsistencyMetrics = {
  mean_score?: number;
  std_deviation?: number;
  coefficient_of_variation?: number;
  consistency_rating?: string;
  min_score?: number;
  max_score?: number;
  score_range?: number;
  iqr?: number;
  error?: string;
};

export type SpecialMatchRow = {
  Season?: string;
  League?: string;
  Week?: number;
  Score?: number;
  Opponent?: string;
  OpponentScore?: number;
  WinMargin?: number;
};

export type SpecialMatches = {
  highest_scores?: SpecialMatchRow[];
  lowest_scores?: SpecialMatchRow[];
  biggest_win_margin?: SpecialMatchRow[];
  biggest_loss_margin?: SpecialMatchRow[];
};

export function useTeams() {
  const database = teamQueryDatabase();
  return useQuery({
    queryKey: ["team", "list", database],
    queryFn: () => fetchJson<string[]>(buildUrl("/team/get_teams")),
    staleTime: TEAM_STALE_MS,
  });
}

export function useTeamSeasons(teamName: string | null) {
  const database = teamQueryDatabase();
  return useQuery({
    queryKey: ["team", "seasons", database, teamName],
    queryFn: () =>
      fetchJson<string[]>(buildUrl("/team/get_available_seasons", { team_name: teamName })),
    enabled: !!teamName,
    staleTime: TEAM_STALE_MS,
  });
}

export function useTeamHistory(teamName: string | null) {
  const database = teamQueryDatabase();
  return useQuery({
    queryKey: ["team", "history", database, teamName],
    queryFn: () => fetchJson<TeamHistory>(buildUrl("/team/get_team_history", { team_name: teamName })),
    enabled: !!teamName,
    staleTime: TEAM_STALE_MS,
  });
}

export function useLeagueComparison(teamName: string | null) {
  const database = teamQueryDatabase();
  return useQuery({
    queryKey: ["team", "league-comparison", database, teamName],
    queryFn: () =>
      fetchJson<LeagueComparison>(
        buildUrl("/team/get_league_comparison", { team_name: teamName }),
      ),
    enabled: !!teamName,
    staleTime: TEAM_STALE_MS,
  });
}

export function useClutchAnalysis(
  teamName: string | null,
  season: string | null,
  clutchThreshold = 10,
) {
  const seasonParam = season && season !== "all" ? season : undefined;
  const database = teamQueryDatabase();
  return useQuery({
    queryKey: ["team", "clutch", database, teamName, seasonParam ?? "", clutchThreshold],
    queryFn: () =>
      fetchJson<ClutchAnalysis>(
        buildUrl("/team/get_clutch_analysis", {
          team_name: teamName,
          season: seasonParam,
          clutch_threshold: clutchThreshold,
        }),
      ),
    enabled: !!teamName,
    staleTime: TEAM_STALE_MS,
  });
}

export function useConsistencyMetrics(teamName: string | null, season: string | null) {
  const seasonParam = season && season !== "all" ? season : undefined;
  const database = teamQueryDatabase();
  return useQuery({
    queryKey: ["team", "consistency", database, teamName, seasonParam ?? ""],
    queryFn: () =>
      fetchJson<ConsistencyMetrics>(
        buildUrl("/team/get_consistency_metrics", {
          team_name: teamName,
          season: seasonParam,
        }),
      ),
    enabled: !!teamName,
    staleTime: TEAM_STALE_MS,
  });
}

export function useSpecialMatches(teamName: string | null, season: string | null) {
  const seasonParam = season && season !== "all" ? season : undefined;
  const database = teamQueryDatabase();
  return useQuery({
    queryKey: ["team", "special-matches", database, teamName, seasonParam ?? ""],
    queryFn: () =>
      fetchJson<SpecialMatches>(
        buildUrl("/team/get_special_matches", {
          team_name: teamName,
          season: seasonParam,
        }),
      ),
    enabled: !!teamName,
    staleTime: TEAM_STALE_MS,
  });
}
