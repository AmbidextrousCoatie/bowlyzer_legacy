import { useMemo, useState } from "react";
import { SegmentedControl } from "../../../components/SegmentedControl";
import { EChart } from "../../../lib/charts/EChart";
import {
  buildTournamentOverviewAverageChartOption,
  buildTournamentOverviewAverageGroups,
  type TournamentOverviewAverageMode,
} from "../../../lib/tournamentOverviewChart";
import type { TournamentPodiumGroup } from "../../../hooks/useTournament";

type Props = {
  podiums: TournamentPodiumGroup[];
  t: (key: string, fallback?: string) => string;
};

export function TournamentPodiumAverageChart({ podiums, t }: Props) {
  const [mode, setMode] = useState<TournamentOverviewAverageMode>("winner");
  const groups = useMemo(() => buildTournamentOverviewAverageGroups(podiums), [podiums]);
  const option = useMemo(
    () => buildTournamentOverviewAverageChartOption(groups, mode),
    [groups, mode],
  );

  const modeOptions = useMemo(
    () =>
      [
        { value: "winner" as const, label: t("ui.tournament.overview_mode_winner", "Sieger") },
        { value: "field" as const, label: t("ui.tournament.overview_mode_field", "Turnier") },
      ] satisfies Array<{ value: TournamentOverviewAverageMode; label: string }>,
    [t],
  );

  if (!option) {
    return (
      <p className="text-small text-muted p-4">
        {t(
          "ui.tournament.overview_average_empty",
          "Keine Schnittdaten für die Darstellung vorhanden.",
        )}
      </p>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-end gap-3 border-b border-border px-4 py-3 lg:px-5">
        <span className="text-small font-medium text-muted">
          {t("ui.tournament.overview_average_mode", "Anzeige")}
        </span>
        <SegmentedControl
          value={mode}
          onChange={setMode}
          options={modeOptions}
          ariaLabel={t("ui.tournament.overview_average_mode", "Anzeige")}
        />
      </div>
      <EChart option={option} height={Math.max(400, groups.length * 40)} />
    </div>
  );
}
