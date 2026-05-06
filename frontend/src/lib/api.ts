/**
 * Thin fetch wrapper. The Vite dev server proxies /league, /player, /team,
 * /tournament to Flask (default http://127.0.0.1:5000; see vite.config.ts), so these calls work
 * unchanged in dev. Production wiring depends on how the SPA is served and
 * isn't relevant yet.
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

export function buildUrl(
  path: string,
  params: Record<string, string | number | undefined | null> = {},
): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") {
      search.set(k, String(v));
    }
  });
  if (!search.has("database") && typeof window !== "undefined") {
    const current = new URLSearchParams(window.location.search).get("database");
    if (current) search.set("database", current);
  }
  const qs = search.toString();
  return qs ? `${path}?${qs}` : path;
}
