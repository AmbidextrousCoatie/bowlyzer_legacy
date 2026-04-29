import type { HonorCardView, HonorItem } from "../types";

export function normalizeHonorCards(raw: unknown): HonorCardView[] {
  if (Array.isArray(raw)) {
    return raw.map((item, idx) => normalizeSingleHonorCard(item, `Card ${idx + 1}`));
  }
  if (raw && typeof raw === "object") {
    return Object.entries(raw as Record<string, unknown>).map(([key, value]) =>
      normalizeSingleHonorCard(value, prettifyKey(key)),
    );
  }
  return [];
}

function normalizeSingleHonorCard(rawCard: unknown, fallbackTitle: string): HonorCardView {
  if (!rawCard || typeof rawCard !== "object") {
    return { title: fallbackTitle, items: [], raw: rawCard };
  }
  const obj = rawCard as Record<string, unknown>;
  const title =
    (typeof obj.title === "string" && obj.title) ||
    (typeof obj.name === "string" && obj.name) ||
    fallbackTitle;

  const items: HonorItem[] = [];
  Object.entries(obj).forEach(([key, value]) => {
    if (key === "title" || key === "name") return;
    if (Array.isArray(value)) {
      value.forEach((entry, idx) => {
        if (entry && typeof entry === "object") {
          const text = summarizeObject(entry as Record<string, unknown>);
          items.push({ label: `${prettifyKey(key)} #${idx + 1}`, value: text });
        } else {
          items.push({ label: `${prettifyKey(key)} #${idx + 1}`, value: String(entry) });
        }
      });
      return;
    }
    if (value && typeof value === "object") {
      items.push({ label: prettifyKey(key), value: summarizeObject(value as Record<string, unknown>) });
      return;
    }
    items.push({ label: prettifyKey(key), value: String(value) });
  });

  return { title, items, raw: rawCard };
}

function summarizeObject(obj: Record<string, unknown>): string {
  const preferredKeys = ["player", "team", "name", "score", "average", "points", "value"];
  const preferred = preferredKeys
    .map((k) => obj[k])
    .filter((v) => v !== undefined && v !== null)
    .map((v) => String(v));
  if (preferred.length > 0) return preferred.join(" | ");
  return Object.entries(obj)
    .slice(0, 4)
    .map(([k, v]) => `${prettifyKey(k)}: ${String(v)}`)
    .join(", ");
}

function prettifyKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
