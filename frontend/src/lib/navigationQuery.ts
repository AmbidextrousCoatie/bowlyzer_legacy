/** Query keys owned by `/mannschaft` — drop when navigating elsewhere. */
export const MANNSCHAFT_QUERY_KEYS = ["club", "team"] as const;

/** Tournament name filter on `/turnier` only (`round` is handled separately; Liga reuses it). */
export const TOURNAMENT_QUERY_KEYS = ["tournament"] as const;

/** Tournament player filter on `/turnier` only. */
export const TOURNAMENT_PLAYER_QUERY_KEYS = ["player"] as const;

/** Spieler identity on `/spieler` only (`player` is the tournament alias). */
export const SPIELER_QUERY_KEYS = ["player_name", "player_id"] as const;

/** Return search params appropriate for ``targetPath`` (strip other pages' keys). */
export function searchParamsForPath(
  targetPath: string,
  source: URLSearchParams,
): URLSearchParams {
  const next = new URLSearchParams(source);
  if (!targetPath.startsWith("/mannschaft")) {
    for (const key of MANNSCHAFT_QUERY_KEYS) next.delete(key);
  }
  if (!targetPath.startsWith("/turnier")) {
    for (const key of TOURNAMENT_QUERY_KEYS) next.delete(key);
    for (const key of TOURNAMENT_PLAYER_QUERY_KEYS) next.delete(key);
  }
  if (!targetPath.startsWith("/turnier") && !targetPath.startsWith("/liga")) {
    // Stage filter on Turnier; Spielrunde on Liga — drop when leaving both.
    next.delete("round");
  }
  if (!targetPath.startsWith("/spieler")) {
    for (const key of SPIELER_QUERY_KEYS) next.delete(key);
  }
  return next;
}

export function querySuffixForPath(targetPath: string, source: URLSearchParams): string {
  const s = searchParamsForPath(targetPath, source).toString();
  return s ? `?${s}` : "";
}

export function stripMannschaftQueryKeys(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of MANNSCHAFT_QUERY_KEYS) next.delete(key);
  return next;
}

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
