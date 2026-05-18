import { useQuery } from "@tanstack/react-query";
import { buildTournamentUrl, fetchJson } from "../lib/api";
import type { TableData } from "../lib/datatable/types";

/** List endpoints are backed by server-side CSV revision cache; avoid refetch churn. */
const TOURNAMENT_LIST_STALE_MS = 10 * 60 * 1000;

export type TournamentRound = {
  round_number?: number | string;
  round_name?: string | null;
};

export type TournamentSummaryCard = {
  title?: string | null;
  subtitle?: string | null;
  value?: string | number | null;
};

export type TournamentSummaryCards = {
  cards?: TournamentSummaryCard[];
};

export type TournamentEffortEntry = {
  player?: string | null;
  club?: string | null;
  display_value?: string | number | null;
  value?: string | number | null;
};

export type TournamentBestEffortsSection = {
  scope?: string | null;
  best_games?: TournamentEffortEntry[];
  best_pairs?: TournamentEffortEntry[];
  best_blocks?: TournamentEffortEntry[];
};

export type TournamentBestEfforts = {
  sections?: TournamentBestEffortsSection[];
  n?: number | null;
};

export type TournamentSection = {
  cards: TournamentSummaryCard[];
  leaderboard: TableData;
  round_results: TableData;
  rounds?: TournamentRound[];
  best_efforts?: TournamentBestEfforts;
};

export type TournamentCutLineSeries = {
  key?: string;
  round_number?: number;
  label?: string;
  data?: Array<number | null>;
};

export type TournamentProgressSeries = {
  labels?: string[];
  avg_series?: Array<number | null>;
  position_series?: Array<number | null>;
  game_score_series?: Array<number | null>;
  tournament_leader_avg_series?: Array<number | null>;
  round_end_lines?: Array<number | null>;
  cut_lines_avg?: Array<number | null>;
  cut_lines_position?: Array<number | null>;
  cut_line_series?: TournamentCutLineSeries[];
  cut_lines_avg_dynamic?: Record<string, Array<number | null>>;
  participant_count?: number;
};

export type TournamentPlayerSummary = {
  average?: number | null;
  best_position?: number | null;
  best_position_game?: string | null;
  final_position?: number | null;
};

export type TournamentPlayerHandicapProfile = {
  a_priori_average?: number | null;
  handicap_per_game?: number | null;
  handicap_reference?: number | null;
};

export type TournamentPlayerBestEfforts = {
  highest_game?: {
    score?: number | null;
    stage?: string | null;
    game?: number | string | null;
  } | null;
  highest_pair?: { score?: number | null; stage?: string | null; pair?: string | null } | null;
  highest_block?: { score?: number | null; stage?: string | null } | null;
  handicap_profile?: TournamentPlayerHandicapProfile | null;
};

export type TournamentPlayerCardId =
  | "summary_final_position"
  | "summary_average"
  | "summary_best_position"
  | "best_highest_game"
  | "best_highest_pair"
  | "handicap_profile"
  | "best_highest_block";

export type TournamentPlayerSection = {
  player: string;
  player_club?: string | null;
  player_card_layout?: TournamentPlayerCardId[];
  round_table: TableData;
  best_efforts?: TournamentPlayerBestEfforts;
  progress_series?: TournamentProgressSeries;
  summary?: TournamentPlayerSummary;
};

export function useTournamentSeasons(tournament?: string | null) {
  return useQuery({
    queryKey: ["tournament", "seasons", tournament ?? ""],
    queryFn: () =>
      fetchJson<string[]>(
        buildTournamentUrl("/tournament/get_available_seasons", {
          tournament: tournament ?? undefined,
        }),
      ),
    staleTime: TOURNAMENT_LIST_STALE_MS,
  });
}

export function useTournamentNames(season: string | null) {
  return useQuery({
    queryKey: ["tournament", "tournaments", season],
    queryFn: () =>
      fetchJson<string[]>(buildTournamentUrl("/tournament/get_available_tournaments", { season })),
    enabled: !!season,
    staleTime: TOURNAMENT_LIST_STALE_MS,
  });
}

export function useTournamentRounds(season: string | null, tournament: string | null) {
  return useQuery({
    queryKey: ["tournament", "rounds", season, tournament],
    queryFn: () =>
      fetchJson<TournamentRound[]>(
        buildTournamentUrl("/tournament/get_available_rounds", { season, tournament }),
      ),
    enabled: !!season && !!tournament,
    staleTime: TOURNAMENT_LIST_STALE_MS,
  });
}

export function useTournamentPlayers(
  season: string | null,
  tournament: string | null,
  round: string | null,
) {
  return useQuery({
    queryKey: ["tournament", "players", season, tournament, round ?? ""],
    queryFn: () =>
      fetchJson<string[]>(
        buildTournamentUrl("/tournament/get_available_players", {
          season,
          tournament,
          round: round || undefined,
        }),
      ),
    enabled: !!season && !!tournament,
    staleTime: TOURNAMENT_LIST_STALE_MS,
  });
}

export function useTournamentSection(
  season: string | null,
  tournament: string | null,
  round: string | null,
) {
  return useQuery({
    queryKey: ["tournament", "section", season, tournament, round ?? ""],
    queryFn: () =>
      fetchJson<TournamentSection>(
        buildTournamentUrl("/tournament/get_section", {
          season,
          tournament,
          round: round || undefined,
          n: 5,
        }),
      ),
    enabled: !!season && !!tournament,
  });
}

export function usePlayerSectionForTournament(
  season: string | null,
  tournament: string | null,
  player: string | null,
) {
  return useQuery({
    queryKey: ["tournament", "player-section", season, tournament, player],
    queryFn: () =>
      fetchJson<TournamentPlayerSection>(
        buildTournamentUrl("/tournament/get_player_section", {
          season: season!,
          tournament: tournament!,
          player: player!,
        }),
      ),
    enabled: Boolean(season && tournament && player),
    retry: 1,
  });
}
