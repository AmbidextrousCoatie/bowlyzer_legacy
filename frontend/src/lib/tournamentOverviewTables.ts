import type { TableData } from "../lib/datatable/types";
import type {
  TournamentFinisher,
  TournamentPodiumGroup,
  TournamentPlayerResultRow,
} from "../hooks/useTournament";
import { formatCompetitionLabel } from "./competitionDisplayName";
import { getPaletteColor, toRgba } from "./color-utils";
import type { CellMetadata } from "./datatable/types";

export type PlayerResultsTableMode = "all" | "season" | "tournament";

export type PodiumWideRowLink = {
  season: string;
  tournament: string;
  tournamentFull?: string;
  place1?: string | null;
  place2?: string | null;
  place3?: string | null;
};

// Easy revert: set to false (no highlighting / no metadata emitted).
const ENABLE_RECURRING_PLAYER_HIGHLIGHT = true;

function buildRecurringPlayerColorMap(rowLinks: PodiumWideRowLink[]): Map<string, string> {
  const counts = new Map<string, number>();
  for (const link of rowLinks) {
    for (const name of [link.place1, link.place2, link.place3]) {
      const key = String(name ?? "").trim();
      if (!key || key === "—") continue;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
  }

  const recurring = [...counts.entries()]
    .filter(([, count]) => count >= 2)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "de"));

  const map = new Map<string, string>();
  recurring.forEach(([name], idx) => {
    map.set(name, getPaletteColor(idx));
  });
  return map;
}

function buildRecurringPlayerCellMetadata(
  rowLinks: PodiumWideRowLink[],
  colIndexByField: Record<"place1" | "place2" | "place3", number>,
): CellMetadata | undefined {
  if (!ENABLE_RECURRING_PLAYER_HIGHLIGHT) return undefined;
  const colorByPlayer = buildRecurringPlayerColorMap(rowLinks);
  if (colorByPlayer.size === 0) return undefined;

  const cell_metadata: CellMetadata = {};
  const fields: Array<keyof typeof colIndexByField> = ["place1", "place2", "place3"];

  rowLinks.forEach((link, rowIdx) => {
    fields.forEach((field) => {
      const name = String(link[field] ?? "").trim();
      if (!name || name === "—") return;
      const color = colorByPlayer.get(name);
      if (!color) return;
      const colIdx = colIndexByField[field];
      cell_metadata[`${rowIdx}:${colIdx}`] = {
        borderLeft: `8px solid ${color}`,
        paddingLeft: "12px",
        backgroundColor: toRgba(color, 0.16),
        fontWeight: 600,
      };
    });
  });

  return Object.keys(cell_metadata).length ? cell_metadata : undefined;
}


function playerAtPlace(finishers: TournamentFinisher[], place: number): string {
  const hit = finishers.find((finisher) => finisher.rank === place);
  if (hit?.player?.trim()) return hit.player.trim();
  const byIndex = finishers[place - 1]?.player?.trim();
  return byIndex || "—";
}

function podiumGroupKey(podium: TournamentPodiumGroup): string {
  return podium.tournament_group?.trim() || podium.tournament;
}

export function groupPodiumsByTournament(
  podiums: TournamentPodiumGroup[],
): Map<string, TournamentPodiumGroup[]> {
  const grouped = new Map<string, TournamentPodiumGroup[]>();
  for (const podium of podiums) {
    const key = podiumGroupKey(podium);
    const bucket = grouped.get(key);
    if (bucket) bucket.push(podium);
    else grouped.set(key, [podium]);
  }
  for (const [key, items] of grouped) {
    items.sort((a, b) => b.season.localeCompare(a.season));
    grouped.set(key, items);
  }
  return grouped;
}

export function sortedTournamentNames(grouped: Map<string, TournamentPodiumGroup[]>): string[] {
  return [...grouped.keys()].sort((a, b) => a.localeCompare(b, "de"));
}

export function buildTournamentSeasonPodiumTable(
  podiums: TournamentPodiumGroup[],
  t: (key: string, fallback?: string) => string,
): { tableData: TableData; rowLinks: PodiumWideRowLink[] } {
  const sorted = [...podiums].sort((a, b) => b.season.localeCompare(a.season));
  const rowLinks: PodiumWideRowLink[] = sorted.map((podium) => {
    const finishers = podium.finishers ?? [];
    return {
      season: podium.season,
      tournament: podium.tournament,
      place1: playerAtPlace(finishers, 1),
      place2: playerAtPlace(finishers, 2),
      place3: playerAtPlace(finishers, 3),
    };
  });

  const rows = rowLinks.map((link) => [
    link.season,
    link.place1 ?? "—",
    link.place2 ?? "—",
    link.place3 ?? "—",
  ]);

  const cell_metadata = buildRecurringPlayerCellMetadata(rowLinks, {
    place1: 1,
    place2: 2,
    place3: 3,
  });

  return {
    rowLinks,
    tableData: {
      columns: [
        {
          title: "",
          columns: [
            {
              title: t("ui.tournament.season", "Saison"),
              field: "season",
              align: "left",
              width: "88px",
            },
            {
              title: t("ui.tournament.podium_place_1", "Platz 1"),
              field: "place1",
              align: "left",
              width: "180px",
            },
            {
              title: t("ui.tournament.podium_place_2", "Platz 2"),
              field: "place2",
              align: "left",
              width: "180px",
            },
            {
              title: t("ui.tournament.podium_place_3", "Platz 3"),
              field: "place3",
              align: "left",
              width: "180px",
            },
          ],
        },
      ],
      data: rows,
      row_metadata: rowLinks.map(() => ({ eventNav: true })),
      ...(cell_metadata ? { cell_metadata } : {}),
    },
  };
}

export function buildSeasonPodiumTable(
  podiums: TournamentPodiumGroup[],
  t: (key: string, fallback?: string) => string,
  tournamentAbbreviations?: Record<string, string>,
): { tableData: TableData; rowLinks: PodiumWideRowLink[] } {
  const sorted = [...podiums].sort((a, b) =>
    podiumGroupKey(a).localeCompare(podiumGroupKey(b), "de"),
  );
  const rowLinks: PodiumWideRowLink[] = sorted.map((podium) => {
    const finishers = podium.finishers ?? [];
    return {
      season: podium.season,
      tournament: podium.tournament,
      tournamentFull: podium.tournament,
      place1: playerAtPlace(finishers, 1),
      place2: playerAtPlace(finishers, 2),
      place3: playerAtPlace(finishers, 3),
    };
  });

  const rows = rowLinks.map((link, index) => [
    formatCompetitionLabel(podiumGroupKey(sorted[index]!), {
      isTournament: true,
      tournamentAbbreviations,
    }),
    link.place1 ?? "—",
    link.place2 ?? "—",
    link.place3 ?? "—",
  ]);

  const cell_metadata = buildRecurringPlayerCellMetadata(rowLinks, {
    place1: 1,
    place2: 2,
    place3: 3,
  });

  return {
    rowLinks,
    tableData: {
      columns: [
        {
          title: "",
          columns: [
            {
              title: t("ui.tournament.tournament", "Turnier"),
              field: "tournament",
              align: "left",
              width: "120px",
            },
            {
              title: t("ui.tournament.podium_place_1", "Platz 1"),
              field: "place1",
              align: "left",
              width: "180px",
            },
            {
              title: t("ui.tournament.podium_place_2", "Platz 2"),
              field: "place2",
              align: "left",
              width: "180px",
            },
            {
              title: t("ui.tournament.podium_place_3", "Platz 3"),
              field: "place3",
              align: "left",
              width: "180px",
            },
          ],
        },
      ],
      data: rows,
      row_metadata: rowLinks.map(() => ({ eventNav: true })),
      ...(cell_metadata ? { cell_metadata } : {}),
    },
  };
}

export function isPlayerLink(name: string | null | undefined): name is string {
  const text = String(name ?? "").trim();
  return !!text && text !== "—";
}

export function buildPlayerResultsTableData(
  rows: TournamentPlayerResultRow[],
  mode: PlayerResultsTableMode,
  t: (key: string, fallback?: string) => string,
): TableData {
  const showSeason = mode === "all" || mode === "tournament";
  const showTournament = mode === "all" || mode === "season";

  const columns = [];
  if (showSeason) {
    columns.push({
      title: t("ui.tournament.season", "Saison"),
      field: "season",
      align: "left" as const,
      width: "88px",
    });
  }
  if (showTournament) {
    columns.push({
      title: t("ui.tournament.tournament", "Turnier"),
      field: "tournament",
      align: "left" as const,
      width: "280px",
    });
  }
  columns.push(
    {
      title: "#",
      field: "position",
      align: "center" as const,
      width: "56px",
      decimal_places: 0,
    },
    {
      title: t("ui.player.average_col", "Schnitt"),
      field: "average",
      align: "center" as const,
      width: "72px",
      decimal_places: 1,
    },
  );

  const data = rows.map((row) => {
    const entry: unknown[] = [];
    if (showSeason) entry.push(row.season);
    if (showTournament) entry.push(row.tournament_group?.trim() || row.tournament);
    entry.push(
      row.position == null ? "—" : String(row.position),
      row.average == null ? "—" : row.average.toFixed(1),
    );
    return entry;
  });

  return {
    columns: [{ title: "", columns }],
    data,
  };
}

export function playerResultsTableMode(
  season: string,
  tournament: string,
): PlayerResultsTableMode {
  if (season && !tournament) return "season";
  if (tournament && !season) return "tournament";
  return "all";
}
