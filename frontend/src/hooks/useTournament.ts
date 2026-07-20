import { useQuery } from "@tanstack/react-query";
import { buildTournamentUrl, fetchJson } from "../lib/api";
import type { TableData } from "../lib/datatable/types";

/** List endpoints are backed by server-side CSV revision cache; avoid refetch churn. */
const TOURNAMENT_LIST_STALE_MS = 10 * 60 * 1000;

export type TournamentRound = {
  round_number?: number | string;
  round_name?: string | null;
};

/** Uniform vs spread for numeric handicap fields in format infobox */
export type HandicapFormatBand =
  | { kind: "uniform"; value: number }
  | { kind: "range"; min: number; max: number; mean: number };

/** `/tournament/get_tournament_format` — enriched rounds + KO config summary */
export type TournamentHandicapFormatInfo = {
  used: boolean;
  columns: {
    handicap: boolean;
    apriori_average: boolean;
    handicap_reference: boolean;
  };
  pins: HandicapFormatBand | null;
  a_priori_average: HandicapFormatBand | null;
  handicap_reference: HandicapFormatBand | null;
};

/** Fallback when `/tournament/get_tournament_format` is cached or older backend without `handicap`. */
export const EMPTY_TOURNAMENT_HANDICAP_FORMAT: TournamentHandicapFormatInfo = {
  used: false,
  columns: {
    handicap: false,
    apriori_average: false,
    handicap_reference: false,
  },
  pins: null,
  a_priori_average: null,
  handicap_reference: null,
};

/** `/tournament/get_tournament_format` — enriched rounds + KO config summary */
export type TournamentFormatInfo = {
  round_count: number;
  rounds: Array<{
    round_number: number;
    round_name: string;
    is_ko_finale_cluster?: boolean;
  }>;
  handicap?: TournamentHandicapFormatInfo;
  ko_finale_round_number_in_data?: number | null;
  ko_bracket_format?: string;
  ko_decision_basis?: string;
  ko_finale_series?: string;
  ko_finale_series_label_de?: string;
  ko_finale_series_label_en?: string;
  qualifying_cut_span?: {
    rank: number;
    first_round: number;
    through_round: number;
  } | null;
  qualifying_cut_pair?: { round: number; rank: number } | null;
  qualifying_stages?: Array<{
    round_number: number;
    name: string;
    cut: string;
    cut_basis?: string;
    game_start?: number;
    game_end?: number;
  }>;
  config: Record<string, unknown>;
  config_note?: string | null;
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

/** Shared progress-chart overlays (cut line, tournament leader) — same for all players. */
export type TournamentFieldProgress = {
  labels?: string[];
  tournament_leader_avg_series?: Array<number | null>;
  tournament_lowest_avg_series?: Array<number | null>;
  round_end_lines?: Array<number | null>;
  cut_lines_avg?: Array<number | null>;
  cut_lines_position?: Array<number | null>;
  /** Cut rank threshold per game index (aligns with `labels`) for position-chart tooltips. */
  cut_position_at_game?: Array<number | null>;
  cut_line_series?: TournamentCutLineSeries[];
  cut_lines_avg_dynamic?: Record<string, Array<number | null>>;
  participant_count?: number;
};

export type KoBracketSide = {
  name?: string | null;
  id?: string | null;
  games_won?: number;
  highlight?: boolean;
  /** Final place when this side is eliminated (or wins the final). */
  place?: number;
};

export type KoBracketFieldPlayer = {
  name?: string | null;
  id?: string | null;
  games?: number[];
  total?: number;
  rank?: number;
  advances?: boolean;
  eliminated?: boolean;
  place?: number;
  highlight?: boolean;
};

export type KoBracketMatch = {
  key: string;
  label?: string;
  phase?: string;
  kind?: "pair" | "field";
  series_mode?: string;
  decision_basis?: string;
  side_a: KoBracketSide;
  side_b: KoBracketSide;
  field?: KoBracketFieldPlayer[];
  /** Nested elim games under a single ELIM match. */
  rounds?: KoBracketMatch[];
  advancer?: string | null;
  pin_games?: number[][];
  walkover?: boolean;
  winner?: "a" | "b" | null;
  loser_place?: number;
  winner_place?: number;
  scratch_total_a?: number;
  scratch_total_b?: number;
  scratch_series?: boolean;
  scratch_final?: boolean;
  inferred?: boolean;
  first_game_number?: number;
};

export type KoBracketPlacement = {
  place?: number;
  player?: string;
};

export type KoBracketPayload = {
  matches?: KoBracketMatch[];
  placements?: KoBracketPlacement[];
  finalist_a?: string | null;
  finalist_b?: string | null;
  path_keys_a?: string[];
  path_keys_b?: string[];
  palette_index_a?: number;
  palette_index_b?: number;
  focus_palette_index?: number;
  focus_player?: string;
  ko_finale_series?: string;
  ko_bracket_format?: string;
  ko_decision_basis?: string;
};

export type TournamentSection = {
  cards: TournamentSummaryCard[];
  leaderboard: TableData;
  round_results: TableData;
  rounds?: TournamentRound[];
  best_efforts?: TournamentBestEfforts;
  field_progress?: TournamentFieldProgress;
  ko_bracket?: KoBracketPayload;
  is_ko_finale_round?: boolean;
  ko_finale_round_number?: number | null;
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
  cut_position_at_game?: Array<number | null>;
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
  field_progress?: TournamentFieldProgress;
  summary?: TournamentPlayerSummary;
  ko_bracket?: KoBracketPayload;
};

export type TournamentFinisher = {
  rank: number;
  rank_label?: string;
  player: string;
  club?: string | null;
  average?: number | null;
};

export type TournamentPodiumGroup = {
  season: string;
  tournament: string;
  tournament_group?: string;
  tournament_average?: number | null;
  finishers: TournamentFinisher[];
};

export type TournamentPodiumsPayload = {
  top_n: number;
  podiums: TournamentPodiumGroup[];
};

export type TournamentPlayerResultRow = {
  season: string;
  tournament: string;
  tournament_group?: string;
  position?: number | null;
  average?: number | null;
  club?: string | null;
};

export function useTournamentSeasons(tournament?: string | null, club?: string | null) {
  return useQuery({
    queryKey: ["tournament", "seasons", tournament ?? "", club ?? ""],
    queryFn: () =>
      fetchJson<string[]>(
        buildTournamentUrl("/tournament/get_available_seasons", {
          tournament: tournament ?? undefined,
          club: club || undefined,
        }),
      ),
    staleTime: TOURNAMENT_LIST_STALE_MS,
  });
}

export function useTournamentNames(season: string | null, club?: string | null) {
  return useQuery({
    queryKey: ["tournament", "tournaments", season ?? "", club ?? ""],
    queryFn: () =>
      fetchJson<string[]>(
        buildTournamentUrl("/tournament/get_available_tournaments", {
          season: season || undefined,
          club: club || undefined,
        }),
      ),
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

export function useTournamentFormat(season: string | null, tournament: string | null) {
  return useQuery({
    // Bump when API shape changes (e.g. handicap on get_tournament_format) so TanStack Query refetches.
    queryKey: ["tournament", "format", "v2-handicap", season, tournament],
    queryFn: () =>
      fetchJson<TournamentFormatInfo>(
        buildTournamentUrl("/tournament/get_tournament_format", { season, tournament }),
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
  const needsEventScope = !!round;
  return useQuery({
    queryKey: ["tournament", "players", season ?? "", tournament ?? "", round ?? ""],
    queryFn: () =>
      fetchJson<string[]>(
        buildTournamentUrl("/tournament/get_available_players", {
          season: season || undefined,
          tournament: tournament || undefined,
          round: round || undefined,
        }),
      ),
    enabled: !needsEventScope || (!!season && !!tournament),
    staleTime: TOURNAMENT_LIST_STALE_MS,
  });
}

export function useTournamentPodiums(
  season: string | null,
  tournament: string | null,
  club?: string | null,
) {
  const showOverview = !(season && tournament);
  return useQuery({
    queryKey: ["tournament", "podiums", season ?? "", tournament ?? "", club ?? ""],
    queryFn: () =>
      fetchJson<TournamentPodiumsPayload>(
        buildTournamentUrl("/tournament/get_tournament_podiums", {
          season: season || undefined,
          tournament: tournament || undefined,
          club: club || undefined,
          n: 3,
        }),
      ),
    enabled: showOverview,
    staleTime: TOURNAMENT_LIST_STALE_MS,
  });
}

export function usePlayerTournamentResults(
  player: string | null,
  season: string | null,
  tournament: string | null,
) {
  const showOverview = !!player && !(season && tournament);
  return useQuery({
    queryKey: ["tournament", "player-results", player ?? "", season ?? "", tournament ?? ""],
    queryFn: () =>
      fetchJson<TournamentPlayerResultRow[]>(
        buildTournamentUrl("/tournament/get_player_tournament_results", {
          player: player!,
          season: season || undefined,
          tournament: tournament || undefined,
        }),
      ),
    enabled: showOverview,
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
    queryKey: ["tournament", "player-section", "v4-hcp-per-spiel", season, tournament, player],
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
