/**
 * Thin fetch wrapper. The Vite dev server proxies /league, /player, /team,
 * /tournament to Flask (default http://127.0.0.1:5000; see vite.config.ts), so these calls work
 * unchanged in dev. In production, Flask serves the built SPA from
 * `frontend/dist` on the same origin, so relative API paths still work.
 */

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function fetchJson<T = unknown>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
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

export function buildUrl(
  path: string,
  params: Record<string, string | number | undefined | null> = {},
  options: { scope?: "league" | "tournament" } = {},
): string {
  const scope = options.scope ?? (path.startsWith("/tournament") ? "tournament" : "league");
  const search = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") {
      search.set(k, String(v));
    }
  });
  if (!search.has("database")) {
    const db = resolveDatabaseParam(scope);
    if (db) search.set("database", db);
  }
  const qs = search.toString();
  return qs ? `${path}?${qs}` : path;
}

/** Tournament APIs ignore league ?database=; only explicit tournament source IDs are forwarded. */
export function buildTournamentUrl(
  path: string,
  params: Record<string, string | number | undefined | null> = {},
): string {
  return buildUrl(path, params, { scope: "tournament" });
}
