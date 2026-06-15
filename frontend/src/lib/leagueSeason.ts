import { seasonForUrlQuery } from "./api";

/** URL / filter value: current season (resolved at read time, not rewritten in the URL). */
export const LEAGUE_SEASON_LATEST = "latest";

/** URL / filter value: no season pinned (Alle Saisons). */
export const LEAGUE_SEASON_ALL = "all";

/** Picks the newest season label (matches legacy league-stats-app.js). */
export function pickLatestSeason(seasons: string[]): string | null {
  if (seasons.length === 0) return null;
  return seasons.reduce((a, b) => (String(a) > String(b) ? a : b));
}

export function isLeagueLatestSeason(season: string): boolean {
  return season === LEAGUE_SEASON_LATEST;
}

export function isLeagueAllSeasons(season: string): boolean {
  return season === LEAGUE_SEASON_ALL;
}

/**
 * Season label sent to season-scoped league APIs.
 * - ``latest`` → newest season in data
 * - ``all`` → no season-scoped fetch (use LeagueOverview aggregation endpoints)
 */
export function resolveLeagueApiSeason(
  season: string,
  seasonList: string[],
  _league: string,
): string | null {
  if (!seasonList.length) return null;
  if (isLeagueAllSeasons(season)) return null;
  if (isLeagueLatestSeason(season)) return pickLatestSeason(seasonList);
  return seasonForUrlQuery(season);
}

export function leagueSeasonFilterLabel(
  season: string,
  t: (key: string, fallback?: string) => string,
): string {
  if (isLeagueLatestSeason(season)) return t("season_latest", "Aktuelle Saison");
  if (isLeagueAllSeasons(season)) return t("season_all", "Alle Saisons");
  return season;
}
