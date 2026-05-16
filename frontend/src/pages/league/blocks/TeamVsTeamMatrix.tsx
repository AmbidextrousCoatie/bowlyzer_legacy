import { useEffect, useMemo, useState } from "react";
import { SegmentedControl } from "../../../components/SegmentedControl";
import { DataTable } from "../../../lib/datatable/DataTable";
import type { TeamVsTeamMetric } from "../../../lib/datatable/teamVsTeamFilter";
import type { DataTableOptions, TableData } from "../../../lib/datatable/types";
import { ensureTeamColors, extractTeamNamesFromTablePayload } from "../../../lib/color-utils";
import { useTranslations } from "../../../hooks/useTranslations";
import { teamVsTeamTableOptions } from "../leagueTableOptions";

type QueryState = {
  data: TableData | undefined;
  isPending: boolean;
  isError: boolean;
  error: Error | null;
};

type Props = {
  query: QueryState;
  options?: DataTableOptions;
};

export function TeamVsTeamMatrix({ query, options = teamVsTeamTableOptions }: Props) {
  const { t } = useTranslations();
  const [metric, setMetric] = useState<TeamVsTeamMetric>("points");

  useEffect(() => {
    if (!query.data) return;
    const teams = extractTeamNamesFromTablePayload(query.data);
    if (teams.length > 0) ensureTeamColors(teams, options.teamColorLeague);
  }, [query.data, options.teamColorLeague]);

  const tableOptions = useMemo(
    () => ({ ...options, teamVsTeamMetric: metric }),
    [options, metric],
  );

  const metricOptions = useMemo(
    () => [
      { value: "points" as const, label: t("points_long", "Punkte") },
      { value: "score" as const, label: t("score", "Pins") },
      { value: "both" as const, label: t("both", "Beides") },
    ],
    [t],
  );

  if (query.isPending) {
    return <div className="h-48 rounded-sm border border-border bg-surface-subtle" aria-hidden />;
  }
  if (query.isError) {
    return (
      <div className="rounded-sm border border-danger-fg/40 bg-surface p-6 text-small text-danger-fg">
        {query.error?.message ?? t("error_generic", "Fehler beim Laden")}
      </div>
    );
  }
  if (!query.data?.columns?.length || !query.data.data?.length) {
    return (
      <div className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
        {t("no_data", "Keine Daten vorhanden")}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {query.data.description ? (
          <p className="text-small text-muted">{query.data.description}</p>
        ) : (
          <span />
        )}
        <SegmentedControl
          value={metric}
          onChange={setMetric}
          options={metricOptions}
          ariaLabel={t("team_vs_team_metric_filter", "Matrix anzeigen")}
        />
      </div>
      <DataTable data={query.data} options={tableOptions} />
    </div>
  );
}
