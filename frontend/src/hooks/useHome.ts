import { useQuery } from "@tanstack/react-query";
import { HOME_EVENT_LIMIT, latestEventsFromV1, loadHome, statsFromV1 } from "../lib/homeV1";
import { V1_QUERY_KEY } from "../lib/v1";

export type HomeStats = {
  games: number;
  league_games: number;
  tournament_games: number;
  years: number;
  league_seasons: number;
  tournaments: number;
  players: number;
  /** @deprecated Flask payload — one warehouse in v1 */
  database?: string;
  /** @deprecated Flask payload — one warehouse in v1 */
  tournament_database?: string;
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

const HOME_STALE_MS = 5 * 60_000;

function homeQueryKey(limit: number) {
  return [V1_QUERY_KEY, "home", limit] as const;
}

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
    queryKey: homeQueryKey(HOME_EVENT_LIMIT),
    queryFn: () => loadHome(HOME_EVENT_LIMIT),
    select: statsFromV1,
    staleTime: HOME_STALE_MS,
  });
}

export function useLatestEvents(limit = HOME_EVENT_LIMIT) {
  return useQuery({
    queryKey: homeQueryKey(limit),
    queryFn: () => loadHome(limit),
    select: latestEventsFromV1,
    staleTime: HOME_STALE_MS,
  });
}
