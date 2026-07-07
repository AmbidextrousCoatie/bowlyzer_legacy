import type { PlayerSeasonRow } from "../hooks/usePlayer";
import { getPaletteColor } from "./color-utils";
import {
  getLeagueClusterKey,
  getLeagueClusterLabel,
  getLeagueClusterLongLabel,
  getLeagueGenderScope,
  getLeagueLevel,
} from "./leagueLevel";
import { normalizeTournamentGroupName, tournamentClusterKey } from "./tournamentGroupName";

export type CompetitionBreakdownComponent = {
  name: string;
  games: number;
  pins: number;
  average: number;
};

export type CompetitionBreakdownEntry = {
  id: string;
  name: string;
  /** Long display name for tooltips (e.g. ``Landesliga``, full tournament title). */
  longName: string;
  isTournament: boolean;
  games: number;
  pins: number;
  average: number;
  sharePct: number;
  components: CompetitionBreakdownComponent[];
};

/** How pie slice colors relate to the bar chart palette. */
export type BreakdownPieColorMode = "matchBar" | "sliceOrder";

const OTHER_SLICE_COLOR = "#71717a";

const PIE_MAX_SLICES = 10;

function competitionRows(rows: PlayerSeasonRow[]): PlayerSeasonRow[] {
  return rows.filter((r) => String(r.row_type ?? "").trim() === "competition");
}

function entryKey(row: PlayerSeasonRow): string {
  const name = String(row.competition ?? "").trim();
  const kind = row.is_tournament ? "t" : "l";
  return `${kind}:${name}`;
}

type RawEntry = {
  id: string;
  name: string;
  isTournament: boolean;
  games: number;
  pins: number;
};

function clusterLeagueEntries(entries: RawEntry[]): CompetitionBreakdownEntry[] {
  const clusters = new Map<
    string,
    {
      label: string;
      longName: string;
      components: CompetitionBreakdownComponent[];
      games: number;
      pins: number;
    }
  >();

  for (const entry of entries) {
    const clusterKey = getLeagueClusterKey(entry.name);
    const level = getLeagueLevel(entry.name);
    const gender = getLeagueGenderScope(entry.name);
    const label = level === 99 ? entry.name : getLeagueClusterLabel(level, gender);
    const longName = level === 99 ? entry.name : getLeagueClusterLongLabel(level, gender);
    const average = entry.games > 0 ? entry.pins / entry.games : 0;

    const prev = clusters.get(clusterKey) ?? {
      label,
      longName,
      components: [],
      games: 0,
      pins: 0,
    };
    prev.components.push({
      name: entry.name,
      games: entry.games,
      pins: entry.pins,
      average,
    });
    prev.games += entry.games;
    prev.pins += entry.pins;
    clusters.set(clusterKey, prev);
  }

  return [...clusters.entries()].map(([id, cluster]) => ({
    id,
    name: cluster.label,
    longName: cluster.longName,
    isTournament: false,
    games: cluster.games,
    pins: cluster.pins,
    average: cluster.games > 0 ? cluster.pins / cluster.games : 0,
    sharePct: 0,
    components: cluster.components.sort(
      (a, b) => b.games - a.games || a.name.localeCompare(b.name, "de"),
    ),
  }));
}

function clusterTournamentEntries(entries: RawEntry[]): CompetitionBreakdownEntry[] {
  const clusters = new Map<
    string,
    {
      groupName: string;
      components: CompetitionBreakdownComponent[];
      games: number;
      pins: number;
    }
  >();

  for (const entry of entries) {
    const groupName = normalizeTournamentGroupName(entry.name);
    const clusterKey = tournamentClusterKey(entry.name);
    const average = entry.games > 0 ? entry.pins / entry.games : 0;

    const prev = clusters.get(clusterKey) ?? {
      groupName,
      components: [],
      games: 0,
      pins: 0,
    };
    prev.components.push({
      name: entry.name,
      games: entry.games,
      pins: entry.pins,
      average,
    });
    prev.games += entry.games;
    prev.pins += entry.pins;
    clusters.set(clusterKey, prev);
  }

  return [...clusters.entries()].map(([id, cluster]) => ({
    id,
    name: cluster.groupName,
    longName: cluster.groupName,
    isTournament: true,
    games: cluster.games,
    pins: cluster.pins,
    average: cluster.games > 0 ? cluster.pins / cluster.games : 0,
    sharePct: 0,
    components: cluster.components.sort(
      (a, b) => b.games - a.games || a.name.localeCompare(b.name, "de"),
    ),
  }));
}

export function buildCompetitionBreakdown(
  rows: PlayerSeasonRow[] | null | undefined,
): CompetitionBreakdownEntry[] {
  if (!rows?.length) return [];

  const buckets = new Map<string, RawEntry>();

  for (const row of competitionRows(rows)) {
    const name = String(row.competition ?? "").trim();
    if (!name) continue;
    const key = entryKey(row);
    const games = row.games ?? 0;
    const pins = row.total_pins ?? 0;
    const prev = buckets.get(key) ?? { id: key, name, isTournament: !!row.is_tournament, games: 0, pins: 0 };
    buckets.set(key, {
      id: key,
      name,
      isTournament: prev.isTournament || !!row.is_tournament,
      games: prev.games + games,
      pins: prev.pins + pins,
    });
  }

  const raw = [...buckets.values()];
  if (raw.length === 0) return [];

  const leagueRaw = raw.filter((entry) => !entry.isTournament);
  const tournamentRaw = raw.filter((entry) => entry.isTournament);

  const merged = [
    ...clusterLeagueEntries(leagueRaw),
    ...clusterTournamentEntries(tournamentRaw),
  ];

  const totalGames = merged.reduce((sum, entry) => sum + entry.games, 0);
  if (totalGames <= 0) return [];

  return merged
    .map((entry) => ({
      ...entry,
      sharePct: (entry.games / totalGames) * 100,
    }))
    .sort((a, b) => b.games - a.games || a.name.localeCompare(b.name, "de"));
}

export type PieSlice = {
  id: string;
  name: string;
  games: number;
  sharePct: number;
};

/** Top-N competitions; remainder rolled into one “other” slice. Input order defines slice order. */
export function buildGamesSharePieSlices(entries: CompetitionBreakdownEntry[]): PieSlice[] {
  if (entries.length === 0) return [];
  if (entries.length <= PIE_MAX_SLICES) {
    return entries.map((e) => ({
      id: e.id,
      name: e.name,
      games: e.games,
      sharePct: e.sharePct,
    }));
  }

  const head = entries.slice(0, PIE_MAX_SLICES - 1);
  const tail = entries.slice(PIE_MAX_SLICES - 1);
  const tailGames = tail.reduce((sum, e) => sum + e.games, 0);
  const tailShare = tail.reduce((sum, e) => sum + e.sharePct, 0);

  return [
    ...head.map((e) => ({
      id: e.id,
      name: e.name,
      games: e.games,
      sharePct: e.sharePct,
    })),
    {
      id: "__other__",
      name: "Sonstige",
      games: tailGames,
      sharePct: tailShare,
    },
  ];
}

export function breakdownSortedByAverage(
  entries: CompetitionBreakdownEntry[],
): CompetitionBreakdownEntry[] {
  return [...entries].sort(
    (a, b) => b.average - a.average || b.games - a.games || a.name.localeCompare(b.name, "de"),
  );
}

export function breakdownChartLabel(
  entry: CompetitionBreakdownEntry,
  formatCompetition: (name: string, options?: { isTournament?: boolean }) => string,
): string {
  if (entry.isTournament) {
    return formatCompetition(entry.name, { isTournament: true });
  }
  return entry.name;
}

/** Palette index per breakdown entry, keyed by bar-chart sort order. */
export function buildBreakdownColorById(
  byAverage: CompetitionBreakdownEntry[],
): Map<string, string> {
  const map = new Map<string, string>();
  byAverage.forEach((entry, idx) => {
    map.set(entry.id, getPaletteColor(idx % 10));
  });
  return map;
}

export function breakdownSliceColor(
  sliceId: string,
  sliceIndex: number,
  colorById: Map<string, string>,
  mode: BreakdownPieColorMode,
): string {
  if (sliceId === "__other__") return OTHER_SLICE_COLOR;
  if (mode === "sliceOrder") return getPaletteColor(sliceIndex % 10);
  return colorById.get(sliceId) ?? getPaletteColor(sliceIndex % 10);
}

export function formatBreakdownTooltipHtml(
  entry: CompetitionBreakdownEntry,
  t: (key: string, fallback?: string) => string,
  formatCompetition: (name: string, options?: { isTournament?: boolean }) => string,
): string {
  const lines = [
    `<strong>${entry.longName}</strong>`,
    `${t("ui.player.average_col", "Schnitt")}: <b>${entry.average.toFixed(2)}</b>`,
    `${t("ui.player.games", "Spiele")}: <b>${entry.games}</b>`,
    `${t("ui.player.competition_share", "Anteil")}: <b>${entry.sharePct.toFixed(1)}%</b>`,
  ];

  if (entry.components.length > 0) {
    lines.push("—");
    const tournamentBase =
      entry.isTournament && entry.components.length > 1
        ? formatCompetition(entry.name, { isTournament: true })
        : null;
    for (const component of entry.components) {
      let label: string;
      if (entry.isTournament) {
        const yearMatch = component.name.match(/\s+(20\d{2})\s*$/);
        const yearSuffix = yearMatch?.[1] ? ` ${yearMatch[1]}` : "";
        label =
          tournamentBase && yearSuffix
            ? `${tournamentBase}${yearSuffix}`
            : formatCompetition(component.name, { isTournament: true });
      } else {
        label = formatCompetition(component.name, { isTournament: false });
      }
      lines.push(
        `${label}: <b>${component.average.toFixed(2)}</b> (${component.games} ${t("ui.player.games", "Spiele")})`,
      );
    }
  }

  return lines.join("<br/>");
}
