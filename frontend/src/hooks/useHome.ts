import { useQuery } from "@tanstack/react-query";
import { buildUrl, fetchJson } from "../lib/api";

export type HomeStats = {
  database: string;
  tournament_database: string;
  games: number;
  league_games: number;
  tournament_games: number;
  leagues: number;
  seasons: number;
  tournaments: number;
  players: number;
};

export type LatestEvent = {
  Season: string;
  League: string;
  Week: number | string;
  Date: string;
};

export function useHomeStats() {
  return useQuery({
    queryKey: ["home", "stats"],
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
