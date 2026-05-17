import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import { EChart } from "../../../lib/charts/EChart";
import { buildUrl, fetchJson } from "../../../lib/api";
import { buildPositionHistoryChartOption } from "../../../lib/teamHistoryChart";
import { getClubTeamColor, teamDisplayLabel } from "../../../lib/teamUtils";
import type { TeamHistory } from "../../../hooks/useTeam";

type Props = {
  teams: string[];
  t: (key: string, fallback?: string) => string;
};

export function ClubPositionHistoryChart({ teams, t }: Props) {
  const queries = useQueries({
    queries: teams.map((team) => ({
      queryKey: ["team", "history", team],
      queryFn: () => fetchJson<TeamHistory>(buildUrl("/team/get_team_history", { team_name: team })),
      staleTime: 5 * 60_000,
    })),
  });

  const isPending = queries.some((q) => q.isPending);
  const isError = queries.some((q) => q.isError);

  const seriesList = useMemo(() => {
    return teams
      .map((team, i) => {
        const data = queries[i]?.data;
        if (!data || Object.keys(data).length === 0) return null;
        return {
          id: team,
          label: `${t("team", "Mannschaft")} ${teamDisplayLabel(team)}`,
          color: getClubTeamColor(team),
          history: data,
        };
      })
      .filter((s): s is NonNullable<typeof s> => s != null);
  }, [teams, queries, t]);

  const option = useMemo(() => buildPositionHistoryChartOption(seriesList), [seriesList]);

  if (isPending) {
    return <p className="text-small text-muted p-4">{t("loading", "Laden…")}</p>;
  }

  if (isError) {
    return (
      <p className="text-small text-danger-fg p-4">
        {t("error_generic", "Fehler beim Laden")}
      </p>
    );
  }

  if (!option) {
    return (
      <p className="text-small text-muted p-4">
        {t("no_data", "Keine Daten verfügbar")}
      </p>
    );
  }

  return <EChart option={option} height={Math.max(400, seriesList.length * 40)} />;
}
