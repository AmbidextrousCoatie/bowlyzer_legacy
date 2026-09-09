/**
 * Thin fetch wrapper. The Vite dev server proxies /league, /player, /team,
 * /tournament, /pipeline to Flask (default http://127.0.0.1:5000; see vite.config.ts), so these calls work
 * unchanged in dev. In production, Flask serves the built SPA from
 * `frontend/dist` on the same origin, so relative API paths still work.
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

export async function postJson<T = unknown>(url: string, body: unknown): Promise<T> {
  return fetchJson<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function fetchJson<T = unknown>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    credentials: "same-origin",
    ...init,
  });
  if (!res.ok) {
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
