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
  player_name?: string | null;
};

export type PlayerLifetimeMostImproved = {
  season?: string | null;
  improvement?: number | null;
  player_name?: string | null;
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
  /** Club-history stint label; falls back to ``club`` when absent. */
  history_club?: string | null;
  team_name?: string | null;
  team_number?: number | string | null;
  player_name?: string | null;
  player_id?: string | null;
  games?: number | null;
  total_pins?: number | null;
  average?: number | null;
  vs_last_season?: number | null;
  rank?: number | null;
  competitors?: number | null;
  best_game?: { score?: number | null } | null;
  worst_game?: { score?: number | null } | null;
};

export type PlayerPeriodRow = {
  season?: string | number | null;
  competition?: string | null;
  is_tournament?: boolean | null;
  period_kind?: "week" | "round" | string | null;
  period_value?: string | null;
  period_number?: number | null;
  player_name?: string | null;
  player_id?: string | null;
  games?: number | null;
  average?: number | null;
  club?: string | null;
  team_name?: string | null;
  team_number?: number | string | null;
  row_type?: string | null;
};

export type PlayerStatsResponse = {
  scope?: "all" | "player" | null;
  lifetime?: PlayerLifetimeStats | null;
  seasons?: PlayerSeasonRow[] | null;
  periods?: PlayerPeriodRow[] | null;
  player_competitions?: PlayerSeasonRow[] | null;
  player_season_totals?: PlayerSeasonRow[] | null;
} | null;

export function isAllPlayersScope(stats: PlayerStatsResponse | undefined): boolean {
  return stats?.scope === "all";
}

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
          ...(playerName ? { player_name: playerName } : {}),
          ...(playerId ? { player_id: playerId } : {}),
        }),
      ),
  });
}

export function usePlayerLifetimeStats(playerName: string, playerId: string, season: string) {
  return useQuery({
    queryKey: ["player", "lifetime", playerName, playerId, season],
    queryFn: () =>
      fetchJson<PlayerStatsResponse>(
        buildUrl("/player/get_lifetime_stats", {
          ...(playerName ? { player_name: playerName } : {}),
          ...(playerId ? { player_id: playerId } : {}),
          season: season || "all",
        }),
      ),
  });
}

export type IndividualGameRecord = {
  player_name?: string | null;
  player_id?: string | null;
  score?: number | null;
  date?: string | null;
  season?: string | number | null;
  competition?: string | null;
  is_tournament?: boolean | null;
  club?: string | null;
  team_name?: string | null;
  team_number?: number | null;
  week?: number | null;
  round_number?: number | null;
};

export function useHighestIndividualGames(
  limit = 10,
  options: {
    enabled?: boolean;
    playerName?: string;
    playerId?: string;
    season?: string;
  } = {},
) {
  const {
    enabled = true,
    playerName = "",
    playerId = "",
    season = "all",
  } = options;

  return useQuery({
    queryKey: ["player", "highest-games", limit, playerName, playerId, season],
    queryFn: () =>
      fetchJson<IndividualGameRecord[]>(
        buildUrl("/player/get_highest_individual_games", {
          limit: String(limit),
          ...(playerName ? { player_name: playerName } : {}),
          ...(playerId ? { player_id: playerId } : {}),
          season: season || "all",
        }),
      ),
    staleTime: 5 * 60_000,
    enabled: enabled && limit > 0,
  });
}

export function useClub300Games() {
  return useQuery({
    queryKey: ["player", "club-300"],
    queryFn: () => fetchJson<IndividualGameRecord[]>(buildUrl("/player/get_club_300")),
    staleTime: 5 * 60_000,
  });
}
