import { useMemo } from "react";
import { EChart } from "../../../lib/charts/EChart";
import { buildPositionHistoryChartOption } from "../../../lib/teamHistoryChart";
import { getClubTeamColor } from "../../../lib/teamUtils";
import type { TeamHistory } from "../../../hooks/useTeam";

type Props = {
  teamName: string;
  history: TeamHistory;
  t: (key: string, fallback?: string) => string;
};

export function TeamHistoryChart({ teamName, history, t }: Props) {
  const color = getClubTeamColor(teamName);
  const option = useMemo(
    () =>
      buildPositionHistoryChartOption([{ id: teamName, label: teamName, color, history }]),
    [teamName, history, color, t],
  );

  if (!option) {
    return (
      <p className="text-small text-muted p-4">
        {t("no_data", "Keine Daten verfügbar")}
      </p>
    );
  }

  return <EChart option={option} height={400} />;
}
