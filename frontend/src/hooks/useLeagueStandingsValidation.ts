import { useQuery } from "@tanstack/react-query";
import { buildUrl, fetchJson } from "../lib/api";

export const VALIDATION_ERROR_CATEGORIES = [
  "perfect",
  "corrected",
  "teams",
  "positions",
  "points",
  "pins",
  "weeks",
  "weekly_points",
  "total_points_ref",
  "total_points_comp",
  "points_excel_total",
  "skipped",
] as const;

export type ValidationErrorCategory = (typeof VALIDATION_ERROR_CATEGORIES)[number];

export type StandingsValidationRow = {
  season: string;
  league: string;
  status: "perfect" | "corrected" | "green" | "yellow" | "red" | "skipped" | string;
  reference_source?: string;
  reference_sheet?: string;
  reference_week?: number | null;
  data_format?: string;
  reference_team_count?: number;
  computed_team_count?: number;
  teams_match?: boolean;
  positions_match?: boolean;
  points_match?: boolean;
  pins_match?: boolean;
  missing_in_computed?: string[];
  missing_in_reference?: string[];
  position_mismatches?: string[];
  points_mismatches?: string[];
  pins_mismatches?: string[];
  findings?: string[];
  expected_weeks?: number;
  available_weeks?: number[];
  missing_matchdays?: number[];
  week_coverage_status?: string;
  notes?: string;
  status_raw?: string;
  team_mismatches_raw?: number;
  team_mismatches_after_team_name?: number;
  team_mismatches_final?: number;
  team_resolution_step?: string;
  total_points_reference?: number;
  total_points_computed?: number;
  total_points_expected?: number;
  reference_total_points_ok?: boolean;
  computed_total_points_ok?: boolean;
  points_mismatch_explained_by_total?: boolean;
  points_auto_corrected?: boolean;
  correction_remark?: string;
  weekly_points_findings?: string[];
  error_categories?: string[];
};

export type TournamentQualityRow = {
  season: string;
  event_name: string;
  tournament_group?: string;
  row_count?: number;
  player_count?: number;
  missing_player_id?: number;
  missing_club?: number;
  club_unknown?: number;
  club_resolved?: number;
  club_names_normalized?: number;
  player_id_remap_rows?: number;
  registry_rows_changed?: number;
  same_name_different_ids?: number;
  same_id_different_names?: number;
  status: "green" | "yellow" | "red" | string;
  findings?: string[];
  notes?: string;
};

export type TournamentQualityResponse = {
  generated_at_utc: string;
  source: "report" | "live" | "absent";
  report_present: boolean;
  report_mtime_utc: string | null;
  row_count: number;
  summary: {
    green: number;
    yellow: number;
    red: number;
    detail_rows: number;
  };
  rows: TournamentQualityRow[];
  filters: { season: string | null; event: string | null };
};

export type LeagueStandingsValidationResponse = {
  generated_at_utc: string;
  source: "report" | "live" | "absent";
  report_present: boolean;
  report_mtime_utc: string | null;
  row_count: number;
  summary: {
    perfect: number;
    corrected: number;
    green: number;
    yellow: number;
    red: number;
    skipped: number;
    week_incomplete: number;
  };
  rows: StandingsValidationRow[];
  filters: { season: string | null; league: string | null };
  tournament_quality?: TournamentQualityResponse;
};

const STALE_MS = 10 * 60 * 1000;

export function useLeagueStandingsValidation(filters?: {
  season?: string | null;
  league?: string | null;
}) {
  const season = filters?.season?.trim() || undefined;
  const league = filters?.league?.trim() || undefined;
  const params: Record<string, string> = {};
  if (season) params.season = season;
  if (league) params.league = league;

  return useQuery({
    queryKey: ["league-standings-validation", season ?? "", league ?? ""],
    queryFn: () =>
      fetchJson<LeagueStandingsValidationResponse>(
        buildUrl("/pipeline/league_standings_validation", params),
      ),
    staleTime: STALE_MS,
  });
}
