import { buildUrl } from "./api";
import type { DataOddity, WeekMatrixCell } from "../hooks/useLeague";

function leaguePathParams(
  season: string,
  leagueShort: string,
  longNames: Record<string, string>,
  extra?: Record<string, string>,
): Record<string, string> {
  const params: Record<string, string> = { season, league: leagueShort, ...extra };
  const long = longNames[leagueShort];
  if (long && long !== leagueShort) params.league_long = long;
  return params;
}

/** Deep link from diagnosis matrices into league stats. */
export function leagueDiagnosisPath(
  season: string,
  leagueShort: string,
  longNames: Record<string, string>,
  week?: number | string | null,
): string {
  const params = leaguePathParams(season, leagueShort, longNames);
  if (week != null && String(week) !== "") params.week = String(week);
  return buildUrl("/liga", params);
}

/** Liga · Saison · Team (season team performance, no matchday). */
export function leagueTeamSeasonPath(
  season: string,
  leagueShort: string,
  team: string,
  longNames: Record<string, string>,
): string {
  return buildUrl("/liga", leaguePathParams(season, leagueShort, longNames, { team }));
}

/** Week matrix cell → first missing matchday, or latest available, or season overview. */
export function weekMatrixCellPath(
  season: string,
  leagueShort: string,
  cell: WeekMatrixCell | undefined,
  longNames: Record<string, string>,
): string {
  const missing = cell?.missing_weeks ?? [];
  if (missing.length > 0) {
    return leagueDiagnosisPath(season, leagueShort, longNames, missing[0]);
  }
  const available = cell?.available_weeks ?? [];
  if (available.length > 0) {
    return leagueDiagnosisPath(season, leagueShort, longNames, Math.max(...available));
  }
  return leagueDiagnosisPath(season, leagueShort, longNames);
}

/** Oddity row → Liga view (matchday + team + round when available). */
export function oddityLigaPath(
  oddity: DataOddity,
  longNames: Record<string, string>,
): string | null {
  const params = oddity.deep_link?.params;
  if (!params?.season || !params?.league) return null;
  const extra: Record<string, string> = {};
  if (params.week != null && String(params.week) !== "") extra.week = String(params.week);
  if (params.team) extra.team = params.team;
  if (params.round != null && String(params.round) !== "") extra.round = String(params.round);
  return buildUrl("/liga", leaguePathParams(params.season, params.league, longNames, extra));
}
