import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation, useSearchParams } from "react-router-dom";
import { buildUrl, fetchJson, isTournamentDatabaseId } from "../lib/api";

export type DataSourceInfo = {
  filename: string;
  display_name: string;
  description: string;
  is_default: boolean;
  is_enabled: boolean;
  file_path: string;
};

export type DataSourcesResponse = {
  success: boolean;
  current_source: string;
  current_display_name: string;
  available_sources: string[];
  sources_info: Record<string, DataSourceInfo>;
  message?: string;
};

export function useDatabaseSelection() {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const queryClient = useQueryClient();
  const databaseParam = searchParams.get("database");
  const onTournamentPage = location.pathname.startsWith("/turnier");

  const infoQuery = useQuery({
    queryKey: ["data-sources", databaseParam ?? ""],
    queryFn: () =>
      fetchJson<DataSourcesResponse>(
        buildUrl("/get-data-sources-info", databaseParam ? { database: databaseParam } : {}),
      ),
    staleTime: 60_000,
  });

  const sources = infoQuery.data?.sources_info ?? {};
  const sourceIds = Object.keys(sources).sort((a, b) =>
    (sources[a]?.display_name ?? a).localeCompare(sources[b]?.display_name ?? b),
  );

  const currentId =
    (databaseParam && sources[databaseParam] ? databaseParam : null) ??
    infoQuery.data?.current_source ??
    sourceIds[0] ??
    "";

  useEffect(() => {
    if (onTournamentPage && databaseParam && !isTournamentDatabaseId(databaseParam)) {
      const next = new URLSearchParams(searchParams);
      next.delete("database");
      setSearchParams(next, { replace: true });
      return;
    }
    if (onTournamentPage) return;
    if (!infoQuery.isSuccess || databaseParam || !infoQuery.data?.current_source) return;
    const next = new URLSearchParams(searchParams);
    next.set("database", infoQuery.data.current_source);
    setSearchParams(next, { replace: true });
  }, [
    onTournamentPage,
    infoQuery.isSuccess,
    infoQuery.data,
    databaseParam,
    searchParams,
    setSearchParams,
  ]);

  async function setDatabase(id: string) {
    const next = new URLSearchParams(searchParams);
    if (id) next.set("database", id);
    else next.delete("database");
    setSearchParams(next, { replace: false });

    try {
      await fetch("/switch-database", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ database: id }),
      });
    } catch {
      /* session sync is best-effort; URL param drives API reads */
    }

    await queryClient.invalidateQueries();
  }

  return {
    currentId,
    currentDisplayName:
      sources[currentId]?.display_name ?? infoQuery.data?.current_display_name ?? currentId,
    sources,
    sourceIds,
    setDatabase,
    isLoading: infoQuery.isPending,
    isError: infoQuery.isError,
    error: infoQuery.error,
  };
}
