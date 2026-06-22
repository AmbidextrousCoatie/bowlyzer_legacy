import type { PlayerSeasonRow } from "../hooks/usePlayer";

export type CompetitionBreakdownEntry = {
  id: string;
  name: string;
  isTournament: boolean;
  games: number;
  pins: number;
  average: number;
  sharePct: number;
};

const PIE_MAX_SLICES = 10;

function competitionRows(rows: PlayerSeasonRow[]): PlayerSeasonRow[] {
  return rows.filter((r) => String(r.row_type ?? "").trim() === "competition");
}

function entryKey(row: PlayerSeasonRow): string {
  const name = String(row.competition ?? "").trim();
  const kind = row.is_tournament ? "t" : "l";
  return `${kind}:${name}`;
}

export function buildCompetitionBreakdown(
  rows: PlayerSeasonRow[] | null | undefined,
): CompetitionBreakdownEntry[] {
  if (!rows?.length) return [];

  const buckets = new Map<
    string,
    { name: string; isTournament: boolean; games: number; pins: number }
  >();

  for (const row of competitionRows(rows)) {
    const name = String(row.competition ?? "").trim();
    if (!name) continue;
    const key = entryKey(row);
    const games = row.games ?? 0;
    const pins = row.total_pins ?? 0;
    const prev = buckets.get(key) ?? { name, isTournament: !!row.is_tournament, games: 0, pins: 0 };
    buckets.set(key, {
      name,
      isTournament: prev.isTournament || !!row.is_tournament,
      games: prev.games + games,
      pins: prev.pins + pins,
    });
  }

  const totalGames = [...buckets.values()].reduce((sum, b) => sum + b.games, 0);
  if (totalGames <= 0) return [];

  return [...buckets.entries()]
    .map(([id, bucket]) => ({
      id,
      name: bucket.name,
      isTournament: bucket.isTournament,
      games: bucket.games,
      pins: bucket.pins,
      average: bucket.games > 0 ? bucket.pins / bucket.games : 0,
      sharePct: (bucket.games / totalGames) * 100,
    }))
    .sort((a, b) => b.games - a.games || a.name.localeCompare(b.name, "de"));
}

export type PieSlice = {
  id: string;
  name: string;
  games: number;
  sharePct: number;
};

/** Top-N competitions by games; remainder rolled into one “other” slice. */
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
