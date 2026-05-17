import { useMemo } from "react";
import { DataTable } from "../../../lib/datatable/DataTable";
import { TEAM_COLOR_PALETTES } from "../../../lib/color-utils";
import type { RowMetaEntry, TableData } from "../../../lib/datatable/types";
import type { PlayerSeasonRow } from "../../../hooks/usePlayer";

/** rainbowPastel color 1 (1-based) — season “All Events” summary rows. */
const SEASON_TOTAL_ROW_ACCENT = TEAM_COLOR_PALETTES.rainbowPastel[0];

type Props = {
  seasons: PlayerSeasonRow[];
  selectedPlayerName: string;
  t: (key: string, fallback?: string) => string;
};

export function SeasonStats({ seasons, selectedPlayerName, t }: Props) {
  const tableData = useMemo<TableData>(
    () => buildTableData(seasons, selectedPlayerName, t),
    [seasons, selectedPlayerName, t],
  );

  if (!seasons || seasons.length === 0) {
    return (
      <section>
        <div className="mb-4">
          <p className="text-label uppercase text-muted mb-1.5">
            {t("ui.player.season_stats_title", "Saisonübersicht")}
          </p>
          <h2 className="text-h2">{t("ui.player.season_stats_title", "Saisonübersicht")}</h2>
        </div>
        <div className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
          {t("ui.player.no_season_data", "Keine Saisondaten vorhanden.")}
        </div>
      </section>
    );
  }

  return (
    <section>
      <div className="mb-4">
        <p className="text-label uppercase text-muted mb-1.5">
          {t("ui.player.season_stats_title", "Saisonübersicht")}
        </p>
        <h2 className="text-h2">{t("ui.player.season_stats_title", "Saisonübersicht")}</h2>
      </div>
      <DataTable
        data={tableData}
        options={{
          disablePositionCircle: true,
          enableSpecialRowStyling: false,
          tooltips: true,
          disableTeamColorUpdate: true,
        }}
      />
    </section>
  );
}

function buildTableData(
  seasons: PlayerSeasonRow[],
  selectedPlayerName: string,
  t: (key: string, fallback?: string) => string,
): TableData {
  const databaseParam =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("database")
      : null;

  const rows = seasons.map((season) => [
    season.season ?? "—",
    competitionCellHtml({
      season: season.season,
      competition: season.competition ?? null,
      isTournament: !!season.is_tournament,
      rowType: String(season.row_type ?? ""),
      club: season.club ?? null,
      teamName: season.team_name ?? null,
      teamNumber: season.team_number ?? null,
      database: databaseParam,
      selectedPlayerName,
    }),
    season.row_type === "season_total"
      ? ""
      : `${season.club ?? "—"}${season.team_number ? ` ${season.team_number}` : ""}`,
    season.games ?? 0,
    formatPins(season.total_pins),
    formatAverageWithDelta(season.average ?? null, season.vs_last_season ?? null),
    season.rank != null
      ? `${season.rank}${season.competitors ? ` / ${season.competitors}` : ""}`
      : "—",
    season.best_game?.score ?? "—",
    season.worst_game?.score ?? "—",
  ]);

  const rowMetadata: RowMetaEntry[] = seasons.map((season): RowMetaEntry => {
    if (season.row_type === "season_total") {
      return {
        styling: { fontWeight: "700" },
        rowAccentColor: SEASON_TOTAL_ROW_ACCENT,
      };
    }
    return null;
  });

  return {
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
          { title: t("ui.player.club", "Verein"), field: "club", align: "left" },
          { title: t("ui.player.games", "Spiele"), field: "games", align: "right" },
          {
            title: t("ui.player.total_pins_col", "Pins"),
            field: "total_pins",
            align: "right",
          },
          {
            title: t("ui.player.average_col", "Schnitt"),
            field: "average",
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
  };
}

function formatPins(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return "0";
  if (!Number.isFinite(value)) return String(value);
  return value.toLocaleString("de-DE");
}

function formatAverageWithDelta(avg: number | null, delta: number | null): string {
  if (avg === null || !Number.isFinite(avg)) return "—";
  const base = avg.toFixed(2);
  if (delta === null || !Number.isFinite(delta)) return base;
  const sign = delta > 0 ? "+" : "";
  return `${base} (${sign}${delta.toFixed(2)})`;
}

type CompetitionCellArgs = {
  season: string | number | null | undefined;
  competition: string | null;
  isTournament: boolean;
  rowType: string;
  club: string | null;
  teamName: string | null;
  teamNumber: number | string | null;
  database: string | null;
  selectedPlayerName: string;
};

function competitionCellHtml(args: CompetitionCellArgs): string {
  const label = args.competition || "—";
  if (args.rowType !== "competition" || !args.competition) {
    return escapeHtml(label);
  }
  const qs = new URLSearchParams();
  qs.set("season", String(args.season ?? ""));
  if (args.isTournament) {
    qs.set("tournament", String(args.competition));
    if (args.selectedPlayerName) qs.set("player", args.selectedPlayerName);
  } else {
    qs.set("league", String(args.competition));
    const teamForLink =
      args.teamName ??
      (args.club
        ? `${args.club.trim()}${args.teamNumber ? ` ${args.teamNumber}` : ""}`.trim()
        : "");
    if (teamForLink) qs.set("team", teamForLink);
  }
  if (args.database) qs.set("database", args.database);
  const targetPath = args.isTournament ? "/turnier" : "/liga";
  return `<a href="${targetPath}?${qs.toString()}">${escapeHtml(label)}</a>`;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
