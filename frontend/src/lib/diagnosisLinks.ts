import { buildUrl } from "./api";
import type { WeekMatrixCell } from "../hooks/useLeague";

/** Deep link from diagnosis matrices into league stats. */
export function leagueDiagnosisPath(
  season: string,
  leagueShort: string,
  longNames: Record<string, string>,
  week?: number | string | null,
): string {
  const params: Record<string, string> = { season, league: leagueShort };
  const long = longNames[leagueShort];
  if (long && long !== leagueShort) params.league_long = long;
  if (week != null && String(week) !== "") params.week = String(week);
  return buildUrl("/liga", params);
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
