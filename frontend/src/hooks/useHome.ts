import { useQuery } from "@tanstack/react-query";
import { buildUrl, fetchJson } from "../lib/api";

export type HomeStats = {
  database: string;
  tournament_database: string;
  games: number;
  league_games: number;
  tournament_games: number;
  years: number;
  league_seasons: number;
  tournaments: number;
  players: number;
  /** @deprecated landing-v1 payload */
  seasons?: number;
  /** @deprecated landing-v1 payload */
  leagues?: number;
};

export type LatestEvent = {
  Season: string;
  League: string;
  Week: number | string;
  Date: string;
};

export function resolveHomeStats(stats: HomeStats | undefined) {
  if (!stats) return undefined;
  return {
    ...stats,
    years: stats.years ?? stats.seasons,
    league_seasons: stats.league_seasons,
    tournaments: stats.tournaments,
  };
}

export function useHomeStats() {
  return useQuery({
    queryKey: ["home", "stats", "v2"],
    queryFn: () => fetchJson<HomeStats>(buildUrl("/home/stats")),
    staleTime: 5 * 60_000,
  });
}

export function useLatestEvents(limit = 8) {
  return useQuery({
    queryKey: ["home", "latest-events", limit],
    queryFn: () =>
      fetchJson<LatestEvent[]>(buildUrl("/league/get_latest_events", { limit })),
    staleTime: 60_000,
  });
}
