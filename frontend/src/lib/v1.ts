/**
 * Client for the sibling bowlyzer-api `/api/v1` service.
 *
 * Vite proxies `/api/v1` to that process (default http://127.0.0.1:8080).
 * Do not attach Flask `?database=` or `language=` — one warehouse, SPA i18n.
 */

import { ApiError } from "./api";
import { queryClient } from "./queryClient";

export const V1_QUERY_KEY = "v1";

let seenRevision: string | null = null;

export function v1Revision(): string | null {
  return seenRevision;
}

export function buildV1Url(
  path: string,
  params: Record<string, string | number | boolean | undefined | null> = {},
): string {
  const base = path.startsWith("/") ? path : `/${path}`;
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "" || value === false) continue;
    search.set(key, value === true ? "1" : String(value));
  }
  const qs = search.toString();
  return qs ? `${base}?${qs}` : base;
}

function errorMessage(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object") return fallback;
  const record = body as Record<string, unknown>;
  const err = record.error;
  if (typeof err === "string" && err) return err;
  if (err && typeof err === "object") {
    const nested = err as { message?: unknown };
    if (typeof nested.message === "string" && nested.message) return nested.message;
  }
  if (typeof record.message === "string" && record.message) return record.message;
  return fallback;
}

function noteRevision(header: string | null): void {
  if (!header) return;
  const previous = seenRevision;
  seenRevision = header;
  if (previous && previous !== header) {
    void queryClient.invalidateQueries({ queryKey: [V1_QUERY_KEY] });
  }
}

export async function fetchV1<T = unknown>(
  path: string,
  params: Record<string, string | number | boolean | undefined | null> = {},
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(buildV1Url(path, params), {
    credentials: "same-origin",
    ...init,
  });
  noteRevision(res.headers.get("X-Data-Revision"));

  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }

  if (!res.ok) {
    throw new ApiError(errorMessage(body, `HTTP ${res.status} ${res.statusText}`), res.status);
  }
  return body as T;
}
