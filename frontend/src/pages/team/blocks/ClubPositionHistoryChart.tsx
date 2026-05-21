import { useMemo } from "react";
import { EChart } from "../../../lib/charts/EChart";
import { historyFromMatrixRow } from "../../../lib/clubMatrixHistory";
import { buildPositionHistoryChartOption } from "../../../lib/teamHistoryChart";
import { getClubTeamColor, splitClubAndTeamNumber, teamDisplayLabel } from "../../../lib/teamUtils";
import type { ClubMatrixRow } from "../../../hooks/useLeague";

type Props = {
  teams: string[];
  matrixRows: ClubMatrixRow[];
  matrixSeasons: string[];
  t: (key: string, fallback?: string) => string;
};

export function ClubPositionHistoryChart({ teams, matrixRows, matrixSeasons, t }: Props) {
  const seriesList = useMemo(() => {
    return teams
      .map((team) => {
        const { teamNumber } = splitClubAndTeamNumber(team);
        const row = matrixRows.find(
          (r) =>
            r.team_number === teamNumber ||
            (!teamNumber && r.team_number === "base"),
        );
        if (!row) return null;
        const history = historyFromMatrixRow(row, matrixSeasons);
        if (Object.keys(history).length === 0) return null;
        return {
          id: team,
          label: `${t("team", "Mannschaft")} ${teamDisplayLabel(team)}`,
          color: getClubTeamColor(team),
          history,
        };
      })
      .filter((s): s is NonNullable<typeof s> => s != null);
  }, [teams, matrixRows, matrixSeasons, t]);

  const option = useMemo(() => buildPositionHistoryChartOption(seriesList), [seriesList]);

  if (matrixRows.length === 0 || matrixSeasons.length === 0) {
    return (
      <p className="text-small text-muted p-4">
        {t("no_data", "Keine Daten verfügbar")}
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
