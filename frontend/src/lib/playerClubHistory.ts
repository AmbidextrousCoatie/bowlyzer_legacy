import type { PlayerSeasonRow } from "../hooks/usePlayer";

/** Chronological order for German season labels like "22/23", "25/26". */
function compareSeasonString(a: string, b: string): number {
  const pa = parseSeasonKey(a);
  const pb = parseSeasonKey(b);
  if (pa !== pb) return pa - pb;
  return a.localeCompare(b, "de");
}

function parseSeasonKey(s: string): number {
  const t = String(s ?? "").trim();
  const m = t.match(/^(\d{2})\/(\d{2})$/);
  if (!m) return Number.NEGATIVE_INFINITY;
  return parseInt(m[1], 10) + 100 * 0; // 22 from 22/23
}

export type ClubHistoryRow = {
  club: string;
  /** e.g. "seit 25/26" or "22/23 – 24/25" */
  period: string;
};

/** One club stint across consecutive seasons. */
type Stint = { club: string; seasons: string[] };

function normalizeClubLabel(raw: string | null | undefined): string | null {
  const s = String(raw ?? "").trim();
  if (!s || s === "-" || s === "—") return null;
  return s;
}

/** Prefer league (non-tournament) competition row when multiple exist per season. */
function resolveClubForSeason(
  rows: PlayerSeasonRow[] | null | undefined,
  season: string,
): string | null {
  if (!rows?.length) return null;
  const needle = String(season).trim();
  const forSeason = rows.filter((r) => {
    if (String(r.season ?? "").trim() !== needle) return false;
    if (String(r.row_type ?? "").trim() !== "competition") return false;
    const c = normalizeClubLabel(r.club);
    return Boolean(c);
  });
  if (forSeason.length === 0) return null;
  const leagueFirst = forSeason.find((r) => !r.is_tournament);
  const pick = leagueFirst ?? forSeason[0];
  return normalizeClubLabel(pick.club);
}

function collectSortedSeasons(rows: PlayerSeasonRow[]): string[] {
  const seasons = new Set<string>();
  for (const r of rows) {
    if (String(r.row_type ?? "").trim() !== "competition") continue;
    if (!normalizeClubLabel(r.club)) continue;
    const s = r.season;
    if (s === undefined || s === null || String(s).trim() === "") continue;
    seasons.add(String(s).trim());
  }
  return [...seasons].sort(compareSeasonString);
}

function buildStints(rows: PlayerSeasonRow[], sortedSeasons: string[]): Stint[] {
  const stints: Stint[] = [];
  let run: Stint | null = null;

  for (const s of sortedSeasons) {
    const club = resolveClubForSeason(rows, s);
    if (!club) {
      if (run) {
        stints.push(run);
        run = null;
      }
      continue;
    }
    if (run && run.club === club) {
      run.seasons.push(s);
    } else {
      if (run) stints.push(run);
      run = { club, seasons: [s] };
    }
  }
  if (run) stints.push(run);
  return stints;
}

function formatPeriod(from: string, to: string, isLatest: boolean): string {
  if (from === to) {
    return isLatest ? `seit ${from}` : from;
  }
  return `${from} – ${to}`;
}

/**
 * Latest chronological stint → first table row; club for page headline = latest stint's club.
 */
export function buildPlayerClubHistory(rows: PlayerSeasonRow[] | null | undefined): {
  currentClub: string | null;
  historyRows: ClubHistoryRow[];
} {
  if (!rows?.length) {
    return { currentClub: null, historyRows: [] };
  }

  const sortedSeasons = collectSortedSeasons(rows);
  if (sortedSeasons.length === 0) {
    return { currentClub: null, historyRows: [] };
  }

  const stints = buildStints(rows, sortedSeasons);
  if (stints.length === 0) {
    return { currentClub: null, historyRows: [] };
  }

  const latest = stints[stints.length - 1];
  const displayStints = [...stints].reverse();

  const historyRows: ClubHistoryRow[] = displayStints.map((st, idx) => {
    const isLatest = idx === 0;
    const from = st.seasons[0];
    const to = st.seasons[st.seasons.length - 1];
    return {
      club: st.club,
      period: formatPeriod(from, to, isLatest),
    };
  });

  return {
    currentClub: latest.club,
    historyRows,
  };
}
