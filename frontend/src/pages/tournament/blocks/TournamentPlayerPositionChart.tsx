import { useMemo } from "react";
import { EChart } from "../../../lib/charts/EChart";
import {
  buildTournamentPositionHistoryChartOption,
  buildTournamentPositionSeries,
} from "../../../lib/tournamentHistoryChart";
import type { TournamentPlayerResultRow } from "../../../hooks/useTournament";

type Props = {
  rows: TournamentPlayerResultRow[];
  t: (key: string, fallback?: string) => string;
};

export function TournamentPlayerPositionChart({ rows, t }: Props) {
  const seriesList = useMemo(() => buildTournamentPositionSeries(rows), [rows]);
  const option = useMemo(
    () => buildTournamentPositionHistoryChartOption(seriesList),
    [seriesList],
  );

  if (!option) {
    return (
      <p className="text-small text-muted p-4">
        {t(
          "ui.tournament.player_position_history_empty",
          "Keine Platzierungsdaten für die Darstellung vorhanden.",
        )}
      </p>
    );
  }

  return (
    <EChart
      option={option}
      height={Math.max(400, seriesList.length * 40)}
    />
  );
}
