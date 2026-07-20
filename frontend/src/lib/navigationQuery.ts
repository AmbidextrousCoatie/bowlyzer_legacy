/**
 * Query keys for `/club` (club overview + team drill-down).
 * `club` is also used on `/diagnose/club-matrix` (multiple `club=` entries).
 * `team` is shared with `/liga` (league Mannschaft filter) — only strip when leaving both.
 *
 * Global ``myClub`` (see ``MY_CLUB_QUERY_KEY``) is intentionally NOT stripped here —
 * it persists across routes until the user clears Mein Club.
 */
export const CLUB_PATH = "/club";

/** @deprecated Legacy path; redirects to {@link CLUB_PATH}. */
export const LEGACY_MANNSCHAFT_PATH = "/mannschaft";

export const CLUB_QUERY_KEYS = ["club", "team"] as const;

/** @deprecated Use {@link CLUB_QUERY_KEYS}. */
export const MANNSCHAFT_QUERY_KEYS = CLUB_QUERY_KEYS;

export function isClubPath(targetPath: string): boolean {
  return (
    targetPath === CLUB_PATH ||
    targetPath.startsWith(`${CLUB_PATH}/`) ||
    targetPath === LEGACY_MANNSCHAFT_PATH ||
    targetPath.startsWith(`${LEGACY_MANNSCHAFT_PATH}/`)
  );
}

/** Tournament name filter on `/turnier` only (`round` is handled separately; Liga reuses it). */
export const TOURNAMENT_QUERY_KEYS = ["tournament"] as const;

/** Tournament player filter on `/turnier` only. */
export const TOURNAMENT_PLAYER_QUERY_KEYS = ["player"] as const;

/** Spieler identity on `/spieler` only (`player` is the tournament alias). */
export const SPIELER_QUERY_KEYS = ["player_name", "player_id"] as const;

/** Liga drill-down on `/liga` only (`season` is also used on `/club` and `/turnier`). */
export const LIGA_QUERY_KEYS = ["league", "week", "division"] as const;

const SEASON_QUERY_SCOPES = [
  "/liga",
  "/club",
  "/turnier",
  "/spieler",
  "/diagnose/validierung",
  "/diagnose/liga-validierung",
] as const;

/** Liga-Validierung page filters (not shared with other routes). */
export const STANDINGS_VALIDATION_QUERY_KEYS = [
  "non_green",
  "weeks_complete",
  "categories",
  "statuses",
] as const;

function keepsSeasonQuery(targetPath: string): boolean {
  return SEASON_QUERY_SCOPES.some(
    (prefix) => targetPath === prefix || targetPath.startsWith(`${prefix}/`),
  );
}

function keepsStandingsValidationQuery(targetPath: string): boolean {
  return (
    targetPath === "/diagnose/validierung" ||
    targetPath.startsWith("/diagnose/validierung/") ||
    targetPath === "/diagnose/liga-validierung" ||
    targetPath.startsWith("/diagnose/liga-validierung/")
  );
}

/** Return search params appropriate for ``targetPath`` (strip other pages' keys). */
export function searchParamsForPath(targetPath: string, source: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(source);
  const onClub = isClubPath(targetPath);
  const onClubMatrixDx = targetPath.startsWith("/diagnose/club-matrix");
  const onLiga = targetPath.startsWith("/liga");
  if (!onClub && !onClubMatrixDx) {
    next.delete("club");
  }
  if (!onClub && !onLiga) {
    next.delete("team");
  }
  if (!onLiga) {
    for (const key of LIGA_QUERY_KEYS) next.delete(key);
    next.delete("week");
  }
  if (!targetPath.startsWith("/turnier")) {
    for (const key of TOURNAMENT_QUERY_KEYS) next.delete(key);
    for (const key of TOURNAMENT_PLAYER_QUERY_KEYS) next.delete(key);
  }
  if (!targetPath.startsWith("/turnier") && !onLiga) {
    next.delete("round");
  }
  if (!targetPath.startsWith("/spieler")) {
    for (const key of SPIELER_QUERY_KEYS) next.delete(key);
  }
  if (!keepsSeasonQuery(targetPath)) {
    next.delete("season");
  }
  if (!keepsStandingsValidationQuery(targetPath)) {
    for (const key of STANDINGS_VALIDATION_QUERY_KEYS) next.delete(key);
  }
  return next;
}

export function querySuffixForPath(targetPath: string, source: URLSearchParams): string {
  const s = searchParamsForPath(targetPath, source).toString();
  return s ? `?${s}` : "";
}

export function stripClubQueryKeys(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of CLUB_QUERY_KEYS) next.delete(key);
  return next;
}

/** @deprecated Use {@link stripClubQueryKeys}. */
export const stripMannschaftQueryKeys = stripClubQueryKeys;

export function stripTournamentQueryKeys(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of TOURNAMENT_QUERY_KEYS) next.delete(key);
  for (const key of TOURNAMENT_PLAYER_QUERY_KEYS) next.delete(key);
  next.delete("round");
  return next;
}

export function stripTournamentPlayerQueryKeys(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of TOURNAMENT_PLAYER_QUERY_KEYS) next.delete(key);
  return next;
}

export function stripSpielerQueryKeys(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of SPIELER_QUERY_KEYS) next.delete(key);
  return next;
}

export function stripLigaQueryKeys(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of LIGA_QUERY_KEYS) next.delete(key);
  next.delete("week");
  next.delete("round");
  return next;
}
