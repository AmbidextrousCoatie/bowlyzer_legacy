import { useQuery } from "@tanstack/react-query";
import { loadClub300Games } from "../lib/club300V1";
import { PLAYER_HIGHLIGHTS_TOP_N_ALL } from "../lib/playerHighlights";
import {
  loadHighestIndividualGames,
  loadPlayerLifetimeStats,
  loadPlayerSearch,
  loadPlayerSeasons,
} from "../lib/playerV1";
import { V1_QUERY_KEY } from "../lib/v1";

export type PlayerSearchEntry = {
  id: string;
  name: string;
  aliases?: string[];
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

export function usePlayerSearch(club?: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "player", "search", club ?? ""],
    queryFn: () => loadPlayerSearch(club),
    staleTime: 5 * 60_000,
  });
}

export function usePlayerSeasons(playerName: string, playerId: string, club?: string | null) {
  const clubFilter = !playerName && !playerId ? club || undefined : undefined;
  return useQuery({
    queryKey: [V1_QUERY_KEY, "player", "seasons", playerName, playerId, clubFilter ?? ""],
    queryFn: () => loadPlayerSeasons(playerName, playerId, clubFilter),
  });
}

export function usePlayerLifetimeStats(
  playerName: string,
  playerId: string,
  season: string,
  club?: string | null,
) {
  const clubFilter = !playerName && !playerId ? club || undefined : undefined;
  const topN = !playerName && !playerId ? PLAYER_HIGHLIGHTS_TOP_N_ALL : undefined;
  return useQuery({
    queryKey: [
      V1_QUERY_KEY,
      "player",
      "lifetime",
      playerName,
      playerId,
      season,
      clubFilter ?? "",
      topN ?? "",
    ],
    queryFn: () => loadPlayerLifetimeStats(playerName, playerId, season, clubFilter, topN),
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
    club?: string | null;
  } = {},
) {
  const { enabled = true, playerName = "", playerId = "", season = "all", club = null } = options;

  const clubFilter = !playerName && !playerId ? club || undefined : undefined;

  return useQuery({
    queryKey: [
      V1_QUERY_KEY,
      "player",
      "highest-games",
      limit,
      playerName,
      playerId,
      season,
      clubFilter ?? "",
    ],
    queryFn: () =>
      loadHighestIndividualGames({
        limit,
        playerName,
        playerId,
        season,
        club: clubFilter,
      }),
    staleTime: 5 * 60_000,
    enabled: enabled && limit > 0,
  });
}

export function useClub300Games(club?: string | null) {
  return useQuery({
    queryKey: [V1_QUERY_KEY, "honor", "300", club ?? ""],
    queryFn: () => loadClub300Games(club),
    staleTime: 5 * 60_000,
  });
}
