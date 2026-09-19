import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { buildUrl, fetchJson, flaskQueryRetry, postJson } from "../lib/api";

export type ClubNameValidationRow = {
  club_label: string;
  row_count: number;
  proposed_canonical?: string;
  proposed_rule?: string;
  saved_canonical?: string;
  default_canonical?: string;
};

export type ClubNameValidationResponse = {
  generated_at_utc: string;
  source: "report" | "live" | "absent";
  report_present: boolean;
  report_mtime_utc: string | null;
  row_count: number;
  summary: {
    unresolved: number;
    with_proposal: number;
    without_proposal: number;
  };
  canonical_names: string[];
  rows: ClubNameValidationRow[];
  saved_mapping: {
    present: boolean;
    path: string;
    mtime_utc: string | null;
    row_count: number;
  };
  club_mapping?: {
    path: string;
    present: boolean;
  };
};

export type ClubNameMappingSaveResponse = {
  ok: boolean;
  path: string;
  row_count: number;
  mtime_utc: string;
  club_mapping?: {
    path: string;
    canonical_count: number;
    aliases_added: number;
    resolved_rows: number;
  };
  clubs_registry?: {
    aliases_added: number;
    skipped_unknown_canonical: number;
    row_count: number;
  };
};

const STALE_MS = 10 * 60 * 1000;

export function useClubNameValidation() {
  return useQuery({
    queryKey: ["club-name-validation"],
    queryFn: () =>
      fetchJson<ClubNameValidationResponse>(buildUrl("/pipeline/club_name_validation")),
    staleTime: STALE_MS,
    retry: flaskQueryRetry,
  });
}

export function useSaveClubNameMappings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (mappings: Array<{ unresolved_label: string; canonical_name: string }>) =>
      postJson<ClubNameMappingSaveResponse>(buildUrl("/pipeline/club_name_validation/save"), {
        mappings,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["club-name-validation"] });
    },
  });
}
