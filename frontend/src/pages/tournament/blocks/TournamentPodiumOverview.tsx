import { useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { CollapsibleSection } from "../../../components/CollapsibleSection";
import { DataTable } from "../../../lib/datatable/DataTable";
import type { DataTableHandle } from "../../../lib/datatable/createDataTable";
import type { DataTableOptions } from "../../../lib/datatable/types";
import { localizeTableData } from "../../../lib/datatable/localizeTableData";
import {
  buildSeasonPodiumTable,
  buildTournamentSeasonPodiumTable,
  groupPodiumsByTournament,
  isPlayerLink,
  sortedTournamentNames,
  type PodiumWideRowLink,
} from "../../../lib/tournamentOverviewTables";
import {
  buildTournamentEventPath,
  buildTournamentPlayerEventPath,
} from "../../../lib/tournamentEventLinks";
import type { TournamentPodiumGroup } from "../../../hooks/useTournament";
import { useTranslations } from "../../../hooks/useTranslations";

type Props = {
  podiums: TournamentPodiumGroup[];
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

export function TournamentPodiumOverview({ podiums, season, tournament, t }: Props) {
  const navigate = useNavigate();
  const { tournamentAbbreviations } = useTranslations();
  const seasonOnly = !!season && !tournament;
  const tournamentOnly = !!tournament && !season;

  if (!podiums.length) {
    return (
      <div className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
        {t("ui.tournament.podium_empty", "Keine Turnierergebnisse für diese Auswahl.")}
      </div>
    );
  }

  if (seasonOnly) {
    const { tableData, rowLinks } = buildSeasonPodiumTable(
      podiums,
      t,
      tournamentAbbreviations,
    );
    return (
      <section className="space-y-4">
        <header>
          <h2 className="text-h2">{t("ui.tournament.podium_heading", "Podium")}</h2>
          <p className="mt-1 text-small text-muted">
            {t("ui.tournament.podium_season_subtitle", "Top 3 je Turnier · Saison {season}").replace(
              "{season}",
              season,
            )}
          </p>
        </header>
        <PodiumWideTable
          tableData={tableData}
          rowLinks={rowLinks}
          showTournamentColumn
          onNavigate={navigate}
          t={t}
        />
      </section>
    );
  }

  const grouped = tournamentOnly
    ? new Map([[tournament, podiums]])
    : groupPodiumsByTournament(podiums);
  const tournamentNames = tournamentOnly ? [tournament] : sortedTournamentNames(grouped);

  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-h2">{t("ui.tournament.podium_heading", "Podium")}</h2>
        <p className="mt-1 text-small text-muted">
          {t("ui.tournament.podium_subtitle", "Top 3 je Saison")}
        </p>
      </header>
      <div className="space-y-4">
        {tournamentNames.map((name, index) => {
          const items = grouped.get(name) ?? [];
          const { tableData, rowLinks } = buildTournamentSeasonPodiumTable(items, t);
          return (
            <CollapsibleSection
              key={name}
              title={name}
              defaultOpen={tournamentOnly || index === 0}
              lazyMount
              expandLabel={t("ui.tournament.expand_podium", "Podium anzeigen")}
              collapseLabel={t("ui.tournament.collapse_podium", "Podium ausblenden")}
            >
              <PodiumWideTable
                tableData={tableData}
                rowLinks={rowLinks}
                onNavigate={navigate}
                t={t}
              />
            </CollapsibleSection>
          );
        })}
      </div>
    </section>
  );
}

function PodiumWideTable({
  tableData,
  rowLinks,
  showTournamentColumn = false,
  onNavigate,
  t,
}: {
  tableData: ReturnType<typeof buildTournamentSeasonPodiumTable>["tableData"];
  rowLinks: PodiumWideRowLink[];
  showTournamentColumn?: boolean;
  onNavigate: (path: string) => void;
  t: (key: string, fallback?: string) => string;
}) {
  const localizedData = useMemo(() => localizeTableData(tableData, t), [tableData, t]);

  const handleTableReady = useCallback(
    (handle: DataTableHandle) => {
      const onCellClick = (
        _e: unknown,
        cell: { getField: () => string; getRow: () => { getData: () => unknown } },
      ) => {
        const field = cell.getField();
        const rowData = cell.getRow().getData() as { __rowIndex?: number };
        const idx = rowData.__rowIndex;
        if (idx == null || typeof idx !== "number") return;
        const link = rowLinks[idx];
        if (!link) return;

        if (field === "tournament" && showTournamentColumn) {
          onNavigate(buildTournamentEventPath(link.season, link.tournament));
          return;
        }

        const placeKey = field as "place1" | "place2" | "place3";
        if (placeKey === "place1" || placeKey === "place2" || placeKey === "place3") {
          const player = link[placeKey];
          if (!isPlayerLink(player)) return;
          onNavigate(buildTournamentPlayerEventPath(link.season, link.tournament, player));
        }
      };
      handle.tabulator.on("cellClick", onCellClick);
    },
    [onNavigate, rowLinks, showTournamentColumn],
  );

  const handleReadyWithTooltips = useCallback(
    (handle: DataTableHandle) => {
      handleTableReady(handle);
      if (!showTournamentColumn) return;
      const rowEls = handle.tabulator.element.querySelectorAll<HTMLElement>(".tabulator-row");
      rowEls.forEach((rowEl, idx) => {
        const link = rowLinks[idx];
        if (!link?.tournamentFull) return;
        const cell = rowEl.querySelector<HTMLElement>(
          '.tabulator-cell[tabulator-field="tournament"]',
        );
        if (cell) cell.setAttribute("title", link.tournamentFull);
      });
    },
    [handleTableReady, rowLinks, showTournamentColumn],
  );

  return (
    <DataTable
      data={localizedData}
      className="has-event-row-navigation min-h-[8rem]"
      options={tableOptions}
      onReady={showTournamentColumn ? handleReadyWithTooltips : handleTableReady}
    />
  );
}
