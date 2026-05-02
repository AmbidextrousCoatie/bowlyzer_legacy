import { DataTable } from "../../../lib/datatable/DataTable";
import {
  useHonorScores,
  useIndividualAverages,
  useLeagueWeekTable,
  useTeamVsTeamComparison,
} from "../../../hooks/useLeague";
import { useTranslations } from "../../../hooks/useTranslations";
import { HonorScoresPanel } from "./HonorScoresPanel";

type Props = {
  season: string;
  league: string;
  week: string;
};

/** Visible when season + league + week are set (no team, no round). */
export function Matchday({ season, league, week }: Props) {
  const { t } = useTranslations();
  const weekTable = useLeagueWeekTable(season, league, week);
  const honor = useHonorScores(season, league, week);
  const teamVsTeam = useTeamVsTeamComparison(season, league, week);
  const individuals = useIndividualAverages(season, league, week);

  return (
    <div className="space-y-12">
      <section>
        <div className="mb-4">
          <p className="text-label uppercase text-muted mb-1.5">
            {t("week", "Spieltag")} {week}
          </p>
          <h2 className="text-h2">{t("match_day_results", "Ergebnisse")}</h2>
        </div>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[2fr_1fr]">
          <DataTableQuery
            query={weekTable}
            options={{
              disablePositionCircle: false,
              enableSpecialRowStyling: true,
              tooltips: true,
            }}
          />
          <HonorScoresPanel
            honorScores={honor.data}
            isPending={honor.isPending}
            isError={honor.isError}
            t={t}
          />
        </div>
      </section>

      <section>
        <div className="mb-4">
          <p className="text-label uppercase text-muted mb-1.5">
            {t("team_vs_team_comparison", "Vergleich")}
          </p>
          <h2 className="text-h2">{t("team_vs_team", "Mannschaft vs. Mannschaft")}</h2>
        </div>
        <DataTableQuery
          query={teamVsTeam}
          options={{
            disablePositionCircle: false,
            enableHeatMap: true,
            tooltips: true,
          }}
        />
      </section>

      <section>
        <div className="mb-4">
          <p className="text-label uppercase text-muted mb-1.5">
            {t("individual_averages", "Einzelschnitte")}
          </p>
          <h2 className="text-h2">{t("best_individual_averages", "Beste Spieler-Schnitte")}</h2>
        </div>
        <DataTableQuery
          query={individuals}
          options={{
            disablePositionCircle: true,
            enableSpecialRowStyling: true,
            tooltips: true,
          }}
        />
      </section>
    </div>
  );
}

function DataTableQuery({
  query,
  options,
}: {
  query: {
    data: import("../../../lib/datatable/types").TableData | undefined;
    isPending: boolean;
    isError: boolean;
    error: Error | null;
  };
  options: import("../../../lib/datatable/types").DataTableOptions;
}) {
  if (query.isPending) {
    return <div className="h-48 rounded-sm border border-border bg-surface-subtle" />;
  }
  if (query.isError) {
    return (
      <div className="rounded-sm border border-danger-fg/40 bg-surface p-6 text-small text-danger-fg">
        {query.error?.message ?? "Fehler beim Laden"}
      </div>
    );
  }
  if (!query.data || !query.data.columns || !query.data.data) {
    return (
      <div className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
        Keine Daten vorhanden.
      </div>
    );
  }
  return <DataTable data={query.data} options={options} />;
}
