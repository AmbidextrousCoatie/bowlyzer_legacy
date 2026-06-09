import { useQuery } from "@tanstack/react-query";
import { buildUrl, fetchJson } from "../lib/api";

export type PipelineArtifact = {
  id: string;
  label: string;
  stream: string;
  source_id: string;
  logical_path: string;
  load_path: string;
  format: string;
  exists: boolean;
  required: boolean;
  status: "ok" | "warn" | "missing" | "absent";
  mtime_utc: string | null;
  size_bytes: number | null;
  row_count: number | null;
};

export type PipelineAppSource = PipelineArtifact & {
  source_id: string;
  display_name: string;
  description: string;
  is_default: boolean;
  is_enabled: boolean;
  filename: string;
};

export type PipelineStatusResponse = {
  generated_at_utc: string;
  paths: {
    published_data_dir: string;
    work_data_dir: string;
    work_dir_readable: boolean;
  };
  last_publish_mtime_utc: string | null;
  published_artifacts: PipelineArtifact[];
  app_sources: PipelineAppSource[];
  config_fingerprints: Record<string, string | Record<string, unknown>>;
  audits: Record<
    string,
    {
      path: string;
      exists: boolean;
      mtime_utc?: string | null;
      size_bytes?: number | null;
      detail_rows?: number | null;
    }
  >;
  docs: Record<string, string>;
};

const STALE_MS = 10 * 60 * 1000;

export function usePipelineStatus() {
  return useQuery({
    queryKey: ["pipeline-status"],
    queryFn: () => fetchJson<PipelineStatusResponse>(buildUrl("/pipeline/status")),
    staleTime: STALE_MS,
  });
}
