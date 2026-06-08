import { useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useClubPlayerResults } from "../../../hooks/useLeague";
import { buildUrl } from "../../../lib/api";
import { DataTable } from "../../../lib/datatable/DataTable";
import type { DataTableHandle } from "../../../lib/datatable/createDataTable";
import { localizeTableData } from "../../../lib/datatable/localizeTableData";
import { rankedTeamTableOptions } from "../../league/leagueTableOptions";

type Props = {
  club: string;
  t: (key: string, fallback?: string) => string;
};

export function ClubPlayerResults({ club, t }: Props) {
  const navigate = useNavigate();
  const query = useClubPlayerResults(club);

  const tableData = useMemo(() => {
    const raw = query.data?.table;
    if (!raw?.data?.length) return null;
    return localizeTableData(raw, t);
  }, [query.data?.table, t]);

  const handleTableReady = useCallback(
    (handle: DataTableHandle) => {
      const onCellClick = (_e: unknown, cell: { getField: () => string; getRow: () => { getData: () => unknown } }) => {
        if (cell.getField() !== "player_name") return;
        const row = cell.getRow().getData() as { player_name?: string; player_id?: string };
        const name = String(row.player_name ?? "").trim();
        if (!name) return;
        navigate(
          buildUrl("/spieler", {
            club,
            player_name: name,
            player_id: row.player_id || undefined,
          }),
        );
      };
      handle.tabulator.on("cellClick", onCellClick);
    },
    [club, navigate],
  );

  return (
    <section className="rounded-sm border border-border bg-surface">
      <header className="border-b border-border px-4 py-3 lg:px-5">
        <h2 className="text-h3">
          {t("ui.team.club_player_results_heading", "Spielerergebnisse im Club")}
        </h2>
        <p className="text-small text-muted mt-1">
          {t(
            "ui.team.club_player_results_hint",
            "Liga-Spiele in dieser Club-Zugehörigkeit — eine Zeile pro Spieler.",
          )}
        </p>
      </header>

      {query.isPending ? (
        <p className="text-small text-muted px-4 py-4 lg:px-5">
          {t("ui.team.club_player_results_loading", "Spielertabelle wird geladen…")}
        </p>
      ) : query.isError ? (
        <p className="text-small text-muted px-4 py-4 lg:px-5">
          {t("ui.team.club_player_results_error", "Spielertabelle konnte nicht geladen werden.")}
        </p>
      ) : !tableData ? (
        <p className="text-small text-muted px-4 py-4 lg:px-5">
          {t("ui.team.club_player_results_empty", "Keine Spielerdaten für diesen Club.")}
        </p>
      ) : (
        <div className="overflow-x-auto px-4 py-4 lg:px-5">
          <DataTable
            data={tableData}
            className="club-player-results-table"
            options={{
              ...rankedTeamTableOptions,
              disablePositionCircle: true,
              enableSpecialRowStyling: false,
              disableTeamColorUpdate: true,
            }}
            onReady={handleTableReady}
          />
        </div>
      )}
    </section>
  );
}
