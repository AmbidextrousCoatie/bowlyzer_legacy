import { useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { DataTable } from "../../lib/datatable/DataTable";
import type { DataTableHandle } from "../../lib/datatable/createDataTable";
import type { DataTableOptions } from "../../lib/datatable/types";
import type { IndividualGameRecord } from "../../hooks/usePlayer";
import { buildClub300TableData } from "../../lib/club300Analytics";

type Props = {
  games: IndividualGameRecord[];
  database: string | null;
  tournamentAbbreviations?: Record<string, string>;
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

export function Club300GamesTable({
  games,
  database,
  tournamentAbbreviations,
  t,
}: Props) {
  const navigate = useNavigate();

  const { tableData, eventPaths } = useMemo(
    () =>
      buildClub300TableData(games, {
        selectedPlayerName: "",
        database,
        tournamentAbbreviations,
        t,
      }),
    [games, database, tournamentAbbreviations, t],
  );

  const handleTableReady = useCallback(
    (handle: DataTableHandle) => {
      const onCellClick = (_e: unknown, cell: { getRow: () => { getData: () => unknown } }) => {
        const rowData = cell.getRow().getData() as { __rowIndex?: number };
        const idx = rowData.__rowIndex;
        if (idx == null || typeof idx !== "number") return;
        const path = eventPaths[idx];
        if (path) navigate(path);
      };
      handle.tabulator.on("cellClick", onCellClick);
    },
    [eventPaths, navigate],
  );

  if (!games.length) {
    return (
      <div className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
        {t("ui.club300.empty", "Keine 300er in der aktuellen Datenquelle.")}
      </div>
    );
  }

  return (
    <DataTable
      data={tableData}
      className="has-event-row-navigation"
      options={tableOptions}
      onReady={handleTableReady}
    />
  );
}
