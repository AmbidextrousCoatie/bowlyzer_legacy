import type { ApiResponse } from "../types";

export async function apiGet<T>(path: string, params: Record<string, string | undefined>): Promise<T> {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([k, v]) => {
    if (v && v.length > 0) url.searchParams.set(k, v);
  });
  const res = await fetch(url.pathname + url.search);
  const json = (await res.json()) as ApiResponse<T>;
  if (!("success" in json) || !json.success) {
    const message = "error" in json ? `${json.error.code}: ${json.error.message}` : "Unknown API error";
    throw new Error(message);
  }
  return json.data;
}
