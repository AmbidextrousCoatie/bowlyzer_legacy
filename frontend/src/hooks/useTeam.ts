import { useQuery } from "@tanstack/react-query";
import {
  clutchFromV1,
  consistencyFromV1,
  DEFAULT_CLUTCH_THRESHOLD,
  historyFromV1,
  leagueComparisonFromV1,
  loadTeamDocument,
  loadTeamList,
  seasonsFromV1,
  specialMatchesFromV1,
  teamsFromV1,
} from "../lib/teamV1";
import { V1_QUERY_KEY } from "../lib/v1";

const TEAM_STALE_MS = 5 * 60_000;

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
  Round?: number;
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

function seasonKey(season: string | null | undefined): string {
  return season && season !== "all" ? season : "";
}

function teamDocumentKey(team: string, season = "", threshold = "") {
  return [V1_QUERY_KEY, "teams", "document", team, season, threshold] as const;
}

export function useTeams() {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "teams"],
    queryFn: loadTeamList,
    select: teamsFromV1,
    staleTime: TEAM_STALE_MS,
  });
}

export function useTeamSeasons(teamName: string | null) {
  return useQuery({
    queryKey: teamDocumentKey(teamName ?? ""),
    queryFn: () => loadTeamDocument(teamName!),
    select: seasonsFromV1,
    enabled: !!teamName,
    staleTime: TEAM_STALE_MS,
  });
}

export function useTeamHistory(teamName: string | null) {
  return useQuery({
    queryKey: teamDocumentKey(teamName ?? ""),
    queryFn: () => loadTeamDocument(teamName!),
    select: historyFromV1,
    enabled: !!teamName,
    staleTime: TEAM_STALE_MS,
  });
}

export function useLeagueComparison(teamName: string | null) {
  return useQuery({
    queryKey: teamDocumentKey(teamName ?? ""),
    queryFn: () => loadTeamDocument(teamName!),
    select: leagueComparisonFromV1,
    enabled: !!teamName,
    staleTime: TEAM_STALE_MS,
  });
}

export function useClutchAnalysis(
  teamName: string | null,
  season: string | null,
  clutchThreshold = DEFAULT_CLUTCH_THRESHOLD,
) {
  const seasonParam = seasonKey(season);
  const thresholdKey =
    clutchThreshold === DEFAULT_CLUTCH_THRESHOLD ? "" : String(clutchThreshold);
  return useQuery({
    queryKey: teamDocumentKey(teamName ?? "", seasonParam, thresholdKey),
    queryFn: () =>
      loadTeamDocument(teamName!, {
        season: seasonParam || undefined,
        threshold: clutchThreshold,
      }),
    select: clutchFromV1,
    enabled: !!teamName,
    staleTime: TEAM_STALE_MS,
  });
}

export function useConsistencyMetrics(teamName: string | null, season: string | null) {
  const seasonParam = seasonKey(season);
  return useQuery({
    queryKey: teamDocumentKey(teamName ?? "", seasonParam),
    queryFn: () => loadTeamDocument(teamName!, { season: seasonParam || undefined }),
    select: consistencyFromV1,
    enabled: !!teamName,
    staleTime: TEAM_STALE_MS,
  });
}

export function useSpecialMatches(teamName: string | null, season: string | null) {
  const seasonParam = seasonKey(season);
  return useQuery({
    queryKey: teamDocumentKey(teamName ?? "", seasonParam),
    queryFn: () => loadTeamDocument(teamName!, { season: seasonParam || undefined }),
    select: specialMatchesFromV1,
    enabled: !!teamName,
    staleTime: TEAM_STALE_MS,
  });
}
