import { useCallback, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { buildUrl } from "../../../lib/api";
import { DataTable } from "../../../lib/datatable/DataTable";
import type { DataTableHandle } from "../../../lib/datatable/createDataTable";
import type { DataTableOptions } from "../../../lib/datatable/types";
import { localizeTableData } from "../../../lib/datatable/localizeTableData";
import { buildTournamentPlayerEventPath } from "../../../lib/tournamentEventLinks";
import {
  buildPlayerResultsTableData,
  playerResultsTableMode,
} from "../../../lib/tournamentOverviewTables";
import type { TournamentPlayerResultRow } from "../../../hooks/useTournament";
import { TournamentPlayerPositionChart } from "./TournamentPlayerPositionChart";

type Props = {
  rows: TournamentPlayerResultRow[];
  player: string;
  season: string;
  tournament: string;
  t: (key: string, fallback?: string) => string;
};

const tableOptions: DataTableOptions = {
  disablePositionCircle: true,
  enableSpecialRowStyling: false,
  tooltips: true,
  stripedRows: true,
  stripedColumnGroups: true,
  columnGroupStripeVariant: "league",
  disableTeamColorUpdate: true,
};

export function TournamentPlayerOverview({
  rows,
  player,
  season,
  tournament,
  t,
}: Props) {
  const navigate = useNavigate();
  const mode = playerResultsTableMode(season, tournament);
  const playerProfilePath = useMemo(
    () => buildUrl("/spieler", { player_name: player }),
    [player],
  );

  const tableData = useMemo(
    () => buildPlayerResultsTableData(rows, mode, t),
    [rows, mode, t],
  );
  const localizedData = useMemo(() => localizeTableData(tableData, t), [tableData, t]);

  const handleTableReady = useCallback(
    (handle: DataTableHandle) => {
      const onCellClick = (_e: unknown, cell: { getField: () => string; getRow: () => { getData: () => unknown } }) => {
        const field = cell.getField();
        if (field !== "season" && field !== "tournament") return;
        const rowData = cell.getRow().getData() as { __rowIndex?: number };
        const idx = rowData.__rowIndex;
        if (idx == null || typeof idx !== "number") return;
        const row = rows[idx];
        if (!row) return;

        const params = buildTournamentPlayerEventPath(row.season, row.tournament, player);
        navigate(params);
      };
      handle.tabulator.on("cellClick", onCellClick);
    },
    [navigate, player, rows],
  );

  if (!rows.length) {
    return (
      <div className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
        {t(
          "ui.tournament.player_overview_empty",
          "Keine Turnierteilnahmen für diese Auswahl.",
        )}
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <section className="rounded-sm border border-border bg-surface">
        <header className="border-b border-border px-4 py-3 lg:px-5">
          <h2 className="text-h3">
            {t("ui.tournament.player_position_history", "Platzierungsverlauf")}
          </h2>
          <p className="text-small text-muted mt-1">
            {t(
              "ui.tournament.player_position_history_hint",
              "Turnierplatzierungen nach Saison — niedrigere Zahl ist besser.",
            )}
          </p>
        </header>
        <TournamentPlayerPositionChart rows={rows} t={t} />
      </section>

      <section>
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-h2">
            {t("ui.tournament.player_overview_heading", "Turnierteilnahmen")}
          </h2>
          <p className="mt-1 text-small">
            <Link
              to={playerProfilePath}
              className="text-muted hover:text-accent hover:underline"
            >
              {player}
            </Link>
          </p>
        </div>
        <Link
          to={playerProfilePath}
          className="h-9 rounded-sm border border-border bg-surface px-3 text-small font-medium text-foreground hover:border-border-strong hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          {t("ui.player.profile", "Spielerprofil")}
        </Link>
      </header>
      <DataTable
        data={localizedData}
        className="has-event-row-navigation"
        options={tableOptions}
        onReady={handleTableReady}
      />
      </section>
    </div>
  );
}
