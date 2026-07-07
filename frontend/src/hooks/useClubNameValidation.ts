import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { buildUrl, postJson } from "../lib/api";

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
};

export type ClubNameMappingSaveResponse = {
  ok: boolean;
  path: string;
  row_count: number;
  mtime_utc: string;
};

const STALE_MS = 10 * 60 * 1000;

export function useClubNameValidation() {
  return useQuery({
    queryKey: ["club-name-validation"],
    queryFn: () => fetchClubNameValidation(),
    staleTime: STALE_MS,
  });
}

export function useSaveClubNameMappings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (mappings: Array<{ unresolved_label: string; canonical_name: string }>) =>
      postJson<ClubNameMappingSaveResponse>(
        buildUrl("/pipeline/club_name_validation/save"),
        { mappings },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["club-name-validation"] });
    },
  });
}

async function fetchClubNameValidation(): Promise<ClubNameValidationResponse> {
  const res = await fetch(buildUrl("/pipeline/club_name_validation"), {
    credentials: "same-origin",
  });
  if (!res.ok) {
    let message = `HTTP ${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { error?: string };
      if (body.error) message = body.error;
    } catch {
      /* not JSON */
    }
    throw new Error(message);
  }
  return (await res.json()) as ClubNameValidationResponse;
}
