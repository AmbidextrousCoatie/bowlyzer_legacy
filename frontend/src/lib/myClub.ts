import type { ClubMatrixPayload, ClubMatrixRow } from "../hooks/useLeague";
import { normalizeClubMatrixCell } from "./clubMatrixCell";
import { normalizeUnicodeLabel } from "./teamUtils";

/** Global “Mein Club” lens — persists across routes until cleared. */
export const MY_CLUB_QUERY_KEY = "myClub";

export type ClubLeagueParticipation = {
  /** Seasons where any Mannschaft of the club played. */
  seasons: string[];
  /** League short names (API ``value``) the club played in, any season. */
  leagues: string[];
  /** Map season → set of league short names. */
  leaguesBySeason: Map<string, Set<string>>;
};

function collectLeaguesFromRows(rows: ClubMatrixRow[]): ClubLeagueParticipation {
  const seasons = new Set<string>();
  const leagues = new Set<string>();
  const leaguesBySeason = new Map<string, Set<string>>();

  for (const row of rows) {
    for (const [season, cell] of Object.entries(row.seasons ?? {})) {
      const { items } = normalizeClubMatrixCell(cell);
      if (items.length === 0) continue;
      seasons.add(season);
      let seasonSet = leaguesBySeason.get(season);
      if (!seasonSet) {
        seasonSet = new Set();
        leaguesBySeason.set(season, seasonSet);
      }
      for (const item of items) {
        const league = String(item.league ?? "").trim();
        if (!league) continue;
        leagues.add(league);
        seasonSet.add(league);
      }
    }
  }

  return {
    seasons: [...seasons].sort(),
    leagues: [...leagues].sort(),
    leaguesBySeason,
  };
}

/** Derive league-season participation from ``get_club_matrix`` payload. */
export function participationFromClubMatrix(
  payload: ClubMatrixPayload | undefined | null,
): ClubLeagueParticipation | null {
  if (!payload?.matrix) return null;
  return collectLeaguesFromRows(payload.matrix.rows ?? []);
}

export function leaguesForSeason(
  participation: ClubLeagueParticipation | null,
  season: string | null,
): string[] | null {
  if (!participation) return null;
  if (!season) return participation.leagues;
  const set = participation.leaguesBySeason.get(season);
  return set ? [...set].sort() : [];
}

export function clubMatchesLabel(a: string, b: string): boolean {
  return normalizeUnicodeLabel(a) === normalizeUnicodeLabel(b);
}
