import { DataTable } from "../../../lib/datatable/DataTable";
import { useGameOverview, useGameTeamDetails } from "../../../hooks/useLeague";
import { useTranslations } from "../../../hooks/useTranslations";

type CommonProps = {
  season: string;
  league: string;
  week: string;
  round: string;
};

/** Visible when season + league + week + round are set (no team). */
export function GameOverview({ season, league, week, round }: CommonProps) {
  const { t } = useTranslations();
  const query = useGameOverview(season, league, week, round);
  return (
    <section>
      <div className="mb-4">
        <p className="text-label uppercase text-muted mb-1.5">
          {t("game", "Spiel")} {round} · {t("week", "Spieltag")} {week}
        </p>
        <h2 className="text-h2">{t("game_overview", "Spielübersicht")}</h2>
      </div>
      <DataTableQuery
        query={query}
        options={{
          disablePositionCircle: false,
          enableSpecialRowStyling: true,
          enableHeatMap: true,
          tooltips: true,
        }}
      />
    </section>
  );
}

type TeamProps = CommonProps & { team: string };

/** Visible when season + league + week + team + round are set. */
export function GameTeamDetails({ season, league, week, team, round }: TeamProps) {
  const { t } = useTranslations();
  const query = useGameTeamDetails(season, league, week, team, round);
  return (
    <section>
      <div className="mb-4">
        <p className="text-label uppercase text-muted mb-1.5">
          {team} · {t("game", "Spiel")} {round}
        </p>
        <h2 className="text-h2">{t("game_team_details", "Spieldetails")}</h2>
      </div>
      <DataTableQuery
        query={query}
        options={{
          disablePositionCircle: true,
          enableSpecialRowStyling: true,
          tooltips: true,
        }}
      />
    </section>
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
