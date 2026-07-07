import { useQuery } from "@tanstack/react-query";
import { buildUrl, fetchJson } from "../lib/api";

export type TournamentCoverageStatus =
  | "not_available"
  | "available"
  | "published_flaws"
  | "published_ok";

export type TournamentCoverageCell = {
  tournament_id: string;
  tournament_name: string;
  season: string;
  status: TournamentCoverageStatus;
  sources: string[];
  row_count: number;
  validation_status: string;
  notes: string;
  event_slug?: string;
};

export type TournamentCoverageResponse = {
  generated_at_utc: string;
  seasons: string[];
  tournaments: Array<{
    id: string;
    long_name: string;
    format?: string;
    gender_scope?: string;
  }>;
  cells: TournamentCoverageCell[];
  summary: Record<TournamentCoverageStatus, number>;
  sources: {
    scrape_log_present: boolean;
    gf_input_present: boolean;
    published_present: boolean;
    quality_report_present: boolean;
    download_pairs: number;
    published_pairs: number;
  };
};

const STALE_MS = 10 * 60 * 1000;

export function useTournamentCoverage() {
  return useQuery({
    queryKey: ["tournament-coverage"],
    queryFn: () => fetchJson<TournamentCoverageResponse>(buildUrl("/pipeline/tournament_coverage")),
    staleTime: STALE_MS,
  });
}
