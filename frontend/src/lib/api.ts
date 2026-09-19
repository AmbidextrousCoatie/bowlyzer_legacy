/**
 * Thin fetch wrapper for Flask RPCs. The Vite dev server proxies /league,
 * /player, /team, /tournament, /pipeline to Flask (default
 * http://127.0.0.1:5000; see vite.config.ts) and `/api/v1` to bowlyzer-api
 * (default http://127.0.0.1:8080). Migrated hooks use `fetchV1` in `v1.ts`
 * and do not send `?database=`. Unmigrated hooks keep this Flask helper.
 */

import { readStoredLanguage } from "./language";
import { MY_CLUB_QUERY_KEY } from "./myClub";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/** Shown when a remaining Flask RPC is unreachable (Vite 502 / no process on :5000). */
export const FLASK_UNAVAILABLE_MESSAGE = "Information noch nicht in aktueller API verfügbar";

export function isFlaskUnavailableStatus(status: number): boolean {
  return status === 502 || status === 503 || status === 504;
}

export function isFlaskUnavailableError(error: unknown): boolean {
  if (error instanceof ApiError) return isFlaskUnavailableStatus(error.status);
  return error instanceof Error && error.message === FLASK_UNAVAILABLE_MESSAGE;
}

export function flaskQueryRetry(failureCount: number, error: unknown): boolean {
  if (isFlaskUnavailableError(error)) return false;
  return failureCount < 2;
}

export async function postJson<T = unknown>(url: string, body: unknown): Promise<T> {
  return fetchJson<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function fetchJson<T = unknown>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, {
      credentials: "same-origin",
      ...init,
    });
  } catch {
    throw new ApiError(FLASK_UNAVAILABLE_MESSAGE, 503);
  }
  if (!res.ok) {
    if (isFlaskUnavailableStatus(res.status)) {
      throw new ApiError(FLASK_UNAVAILABLE_MESSAGE, res.status);
    }
    let message = `HTTP ${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { error?: string; message?: string };
      if (body.error) message = body.error;
      else if (body.message) message = body.message;
    } catch {
      /* not JSON */
    }
    throw new ApiError(message, res.status);
  }
  return (await res.json()) as T;
}

export const TOURNAMENT_DATABASE_IDS = new Set([
  "db_tournament_sbm_2026_gf",
  "db_tournament_nbm_2026_gf",
  "db_tournament_regions_2026_gf",
  "db_tournament_geek_2026",
  "db_tournament_myth_2024_2026",
]);

export function isTournamentDatabaseId(id: string | null | undefined): boolean {
  if (!id) return false;
  return id.startsWith("db_tournament") || TOURNAMENT_DATABASE_IDS.has(id);
}

function resolveDatabaseParam(scope: "league" | "tournament"): string | null {
  if (typeof window === "undefined") return null;
  const current = new URLSearchParams(window.location.search).get("database");
  if (!current) return null;
  const isTournamentDb =
    current.startsWith("db_tournament") || TOURNAMENT_DATABASE_IDS.has(current);
  if (scope === "tournament") return isTournamentDb ? current : null;
  return current;
}

const SEASON_LABEL = /^\d{2}[/-]\d{2}$/;

/** Canonical ``10/11`` for React Router / address bar. Accepts legacy ``10-11`` bookmarks. */
export function seasonForUrlQuery(season: string): string {
  const text = season.trim();
  if (SEASON_LABEL.test(text)) return text.replace("-", "/");
  return text;
}

/**
 * Wire format for ``fetch`` query strings behind nginx.
 * Uses ``10-11`` so the proxy does not split ``season=10/11`` into an extra path segment.
 * Flask normalizes back to ``10/11``.
 */
export function seasonForApiQuery(season: string): string {
  const canon = seasonForUrlQuery(season);
  if (/^\d{2}\/\d{2}$/.test(canon)) return canon.replace("/", "-");
  return canon;
}

function isBackendApiPath(path: string): boolean {
  const p = path.split("?")[0] ?? path;
  return (
    p.startsWith("/league/") ||
    p.startsWith("/team/") ||
    p.startsWith("/player/") ||
    p.startsWith("/tournament/") ||
    p.startsWith("/pipeline/") ||
    p.startsWith("/home/") ||
    p === "/get-data-sources-info" ||
    p === "/switch-database"
  );
}

function formatQueryPair(key: string, value: string, apiWire: boolean): string {
  if (key === "season") {
    const season = apiWire ? seasonForApiQuery(value) : seasonForUrlQuery(value);
    return `season=${season}`;
  }
  return `${encodeURIComponent(key)}=${encodeURIComponent(value)}`;
}

export function buildUrl(
  path: string,
  params: Record<string, string | number | undefined | null> = {},
  options: { scope?: "league" | "tournament" } = {},
): string {
  const scope = options.scope ?? (path.startsWith("/tournament") ? "tournament" : "league");
  const apiWire = isBackendApiPath(path);
  const parts: string[] = [];
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") {
      parts.push(formatQueryPair(k, String(v), apiWire));
    }
  });
  if (!parts.some((p) => p.startsWith("database="))) {
    const db = resolveDatabaseParam(scope);
    if (db) parts.push(formatQueryPair("database", db, apiWire));
  }
  if (apiWire && !parts.some((p) => p.startsWith("language="))) {
    parts.push(formatQueryPair("language", readStoredLanguage(), apiWire));
  }
  if (!apiWire && typeof window !== "undefined") {
    const myClub = new URLSearchParams(window.location.search).get(MY_CLUB_QUERY_KEY)?.trim();
    if (myClub && !parts.some((p) => p.startsWith(`${MY_CLUB_QUERY_KEY}=`))) {
      parts.push(formatQueryPair(MY_CLUB_QUERY_KEY, myClub, false));
    }
  }
  const qs = parts.join("&");
  return qs ? `${path}?${qs}` : path;
}

/** Tournament APIs ignore league ?database=; only explicit tournament source IDs are forwarded. */
export function buildTournamentUrl(
  path: string,
  params: Record<string, string | number | undefined | null> = {},
): string {
  return buildUrl(path, params, { scope: "tournament" });
}
