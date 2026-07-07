import type { TableData } from "../lib/datatable/types";
import type {
  TournamentFinisher,
  TournamentPodiumGroup,
  TournamentPlayerResultRow,
} from "../hooks/useTournament";
import { formatCompetitionLabel } from "./competitionDisplayName";

export type PlayerResultsTableMode = "all" | "season" | "tournament";

export type PodiumWideRowLink = {
  season: string;
  tournament: string;
  tournamentFull?: string;
  place1?: string | null;
  place2?: string | null;
  place3?: string | null;
};


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
