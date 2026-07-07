import { useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
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
    <section>
      <header className="mb-4">
        <h2 className="text-h2">
          {t("ui.tournament.player_overview_heading", "Turnierteilnahmen")}
        </h2>
        <p className="mt-1 text-small text-muted">{player}</p>
      </header>
      <DataTable
        data={localizedData}
        className="has-event-row-navigation"
        options={tableOptions}
        onReady={handleTableReady}
      />
    </section>
  );
}
