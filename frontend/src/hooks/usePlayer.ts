import { useQuery } from "@tanstack/react-query";
import { buildUrl, fetchJson } from "../lib/api";

export type PlayerSearchEntry = {
  id: string;
  name: string;
};

export type PlayerLifetimeBestGame = {
  score?: number | null;
  event?: string | null;
  date?: string | null;
};

export type PlayerLifetimeSeasonRecord = {
  season?: string | null;
  average?: number | null;
};

export type PlayerLifetimeMostImproved = {
  season?: string | null;
  improvement?: number | null;
};

export type PlayerLifetimeStats = {
  total_games?: number | null;
  total_pins?: number | null;
  average_score?: number | null;
  best_game?: PlayerLifetimeBestGame | null;
  best_season?: PlayerLifetimeSeasonRecord | null;
  most_improved?: PlayerLifetimeMostImproved | null;
};

export type PlayerSeasonRowType = "season_total" | "competition";

export type PlayerSeasonRow = {
  season?: string | number | null;
  competition?: string | null;
  is_tournament?: boolean | null;
  row_type?: string | null;
  club?: string | null;
  team_name?: string | null;
  team_number?: number | string | null;
  games?: number | null;
  total_pins?: number | null;
  average?: number | null;
  vs_last_season?: number | null;
  rank?: number | null;
  competitors?: number | null;
  best_game?: { score?: number | null } | null;
  worst_game?: { score?: number | null } | null;
};

export type PlayerStatsResponse = {
  lifetime?: PlayerLifetimeStats | null;
  seasons?: PlayerSeasonRow[] | null;
} | null;

export function usePlayerSearch() {
  return useQuery({
    queryKey: ["player", "search"],
    queryFn: () => fetchJson<PlayerSearchEntry[]>(buildUrl("/player/search")),
    staleTime: 5 * 60_000,
  });
}

export function usePlayerSeasons(playerName: string, playerId: string) {
  return useQuery({
    queryKey: ["player", "seasons", playerName, playerId],
    queryFn: () =>
      fetchJson<string[]>(
        buildUrl("/player/get_available_seasons", {
          player_name: playerName,
          player_id: playerId,
        }),
      ),
    enabled: !!playerName || !!playerId,
  });
}

export function usePlayerLifetimeStats(playerName: string, playerId: string, season: string) {
  return useQuery({
    queryKey: ["player", "lifetime", playerName, playerId, season],
    queryFn: () =>
      fetchJson<PlayerStatsResponse>(
        buildUrl("/player/get_lifetime_stats", {
          player_name: playerName,
          player_id: playerId,
          season: season || "all",
        }),
      ),
    enabled: !!playerName || !!playerId,
  });
}
