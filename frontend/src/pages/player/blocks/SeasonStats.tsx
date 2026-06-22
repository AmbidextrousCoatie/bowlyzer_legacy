import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { DataTable } from "../../../lib/datatable/DataTable";
import type { DataTableHandle } from "../../../lib/datatable/createDataTable";
import { TEAM_COLOR_PALETTES } from "../../../lib/color-utils";
import type { RowMetaEntry, TableData } from "../../../lib/datatable/types";
import type { PlayerSeasonRow } from "../../../hooks/usePlayer";
import {
  buildCompetitionEventPath,
  type CompetitionLinkContext,
} from "../../../lib/playerCompetitionLinks";
import {
  filterSeasonRows,
  formatTeamLabel,
  formatTrendDelta,
  type SeasonTableFilter,
} from "../../../lib/playerHighlights";

/** rainbowPastel color 1 (1-based) — season “All Events” summary rows. */
const SEASON_TOTAL_ROW_ACCENT = TEAM_COLOR_PALETTES.rainbowPastel[0];

type Props = {
  seasons: PlayerSeasonRow[];
  selectedPlayerName: string;
  t: (key: string, fallback?: string) => string;
};

export function SeasonStats({ seasons, selectedPlayerName, t }: Props) {
  const navigate = useNavigate();
  const [tableFilter, setTableFilter] = useState<SeasonTableFilter>("all");

  const databaseParam =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("database")
      : null;

  const filteredSeasons = useMemo(
    () => filterSeasonRows(seasons, tableFilter),
    [seasons, tableFilter],
  );

  const { tableData, eventPaths } = useMemo(
    () => buildTableData(filteredSeasons, selectedPlayerName, databaseParam, t),
    [filteredSeasons, selectedPlayerName, databaseParam, t],
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

  if (!seasons || seasons.length === 0) {
    return (
      <section>
        <div className="mb-4">
          <p className="text-label uppercase text-muted mb-1.5">
            {t("ui.player.season_stats_title", "Saisonübersicht")}
          </p>
          <h2 className="text-h2">{t("ui.player.season_stats_title", "Saisonstatistik")}</h2>
        </div>
        <div className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
          {t("ui.player.no_season_data", "Keine Saisondaten vorhanden.")}
        </div>
      </section>
    );
  }

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-label uppercase text-muted mb-1.5">
            {t("ui.player.season_stats_title", "Saisonübersicht")}
          </p>
          <h2 className="text-h2">{t("ui.player.season_stats_title", "Saisonstatistik")}</h2>
        </div>
        <TableFilterGroup value={tableFilter} onChange={setTableFilter} t={t} />
      </div>
      <DataTable
        data={tableData}
        className="has-event-row-navigation"
        options={{
          disablePositionCircle: true,
          enableSpecialRowStyling: false,
          tooltips: true,
          disableTeamColorUpdate: true,
        }}
        onReady={handleTableReady}
      />
    </section>
  );
}

function TableFilterGroup({
  value,
  onChange,
  t,
}: {
  value: SeasonTableFilter;
  onChange: (value: SeasonTableFilter) => void;
  t: (key: string, fallback?: string) => string;
}) {
  const options: { id: SeasonTableFilter; labelKey: string; fallback: string }[] = [
    { id: "all", labelKey: "ui.player.filter_all_details", fallback: "Alle Details" },
    { id: "league", labelKey: "ui.player.filter_league", fallback: "Liga" },
    { id: "tournaments", labelKey: "ui.player.filter_tournaments", fallback: "Turniere" },
  ];

  return (
    <div
      className="flex flex-wrap gap-1"
      role="group"
      aria-label={t("ui.player.season_table_filter", "Tabellenfilter")}
    >
      {options.map((opt) => (
        <button
          key={opt.id}
          type="button"
          onClick={() => onChange(opt.id)}
          aria-pressed={value === opt.id}
          className={
            "h-9 rounded-sm border px-3 text-small font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring " +
            (value === opt.id
              ? "border-accent bg-accent text-accent-foreground hover:bg-accent-hover"
              : "border-border bg-surface text-foreground hover:border-border-strong")
          }
        >
          {t(opt.labelKey, opt.fallback)}
        </button>
      ))}
    </div>
  );
}

function buildTableData(
  seasons: PlayerSeasonRow[],
  selectedPlayerName: string,
  database: string | null,
  t: (key: string, fallback?: string) => string,
): { tableData: TableData; eventPaths: Array<string | null> } {
  const eventPaths = seasons.map((season) =>
    buildCompetitionEventPath(season, {
      selectedPlayerName,
      database,
    } as CompetitionLinkContext),
  );

  const rows = seasons.map((season) => [
    season.season ?? "—",
    escapeHtml(season.competition || "—"),
    formatAverage(season.average ?? null),
    formatTrendDelta(season.vs_last_season ?? null),
    season.games ?? 0,
    formatTeamLabel(season),
    formatPins(season.total_pins),
    season.rank != null
      ? `${season.rank}${season.competitors ? ` / ${season.competitors}` : ""}`
      : "—",
    season.best_game?.score ?? "—",
    season.worst_game?.score ?? "—",
  ]);

  const rowMetadata: RowMetaEntry[] = seasons.map((season, index): RowMetaEntry => {
    if (season.row_type === "season_total") {
      return { rowAccentColor: SEASON_TOTAL_ROW_ACCENT };
    }
    if (eventPaths[index]) {
      return { eventNav: true };
    }
    return null;
  });

  return {
    tableData: {
      columns: [
        {
          title: "",
          columns: [
            { title: t("ui.player.season", "Saison"), field: "season" },
            {
              title: t("ui.player.competition", "Wettbewerb"),
              field: "competition",
              align: "left",
            },
            {
              title: t("ui.player.average_col", "Schnitt"),
              field: "average",
              align: "right",
            },
            {
              title: t("ui.player.trend_col", "Trend"),
              field: "trend",
              align: "right",
            },
            { title: t("ui.player.games", "Spiele"), field: "games", align: "right" },
            { title: t("ui.player.team_col", "Mannschaft"), field: "team", align: "left" },
            {
              title: t("ui.player.total_pins_col", "Pins gesamt"),
              field: "total_pins",
              align: "right",
            },
            { title: t("ui.player.rank", "Platz"), field: "rank", align: "right" },
            {
              title: t("ui.player.best_game", "Bestes Spiel"),
              field: "best_game",
              align: "right",
            },
            {
              title: t("ui.player.worst_game", "Schlechtestes Spiel"),
              field: "worst_game",
              align: "right",
            },
          ],
        },
      ],
      data: rows,
      row_metadata: rowMetadata,
    },
    eventPaths,
  };
}

function formatPins(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return "0";
  if (!Number.isFinite(value)) return String(value);
  return value.toLocaleString("de-DE");
}

function formatAverage(avg: number | null): string {
  if (avg === null || !Number.isFinite(avg)) return "—";
  return avg.toFixed(2);
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
