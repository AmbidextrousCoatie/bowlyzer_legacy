import type { PlayerSearchEntry } from "../hooks/usePlayer";

/** Display label for combobox rows and the committed selection. */
export function formatPlayerSearchLabel(entry: Pick<PlayerSearchEntry, "name" | "id">): string {
  const name = entry.name.trim();
  const id = String(entry.id ?? "").trim();
  if (!name) return id;
  if (!id) return name;
  return `${name} (${id})`;
}

/** Haystack for fuzzy search — name plus EDV id in one field. */
export function playerSearchHaystack(entry: Pick<PlayerSearchEntry, "name" | "id">): string {
  const name = entry.name.trim();
  const id = String(entry.id ?? "").trim();
  return id ? `${name} ${id}` : name;
}

export function playerSearchEntryMatchesQuery(
  entry: PlayerSearchEntry,
  query: string,
): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  const haystack = playerSearchHaystack(entry).toLowerCase();
  if (haystack.includes(needle)) return true;
  return formatPlayerSearchLabel(entry).toLowerCase().includes(needle);
}

/** Resolve catalog entry — ``player_id`` wins over display name (homonyms). */
export function resolvePlayerSearchEntry(
  players: PlayerSearchEntry[],
  query: { name?: string; id?: string },
): PlayerSearchEntry | null {
  const id = query.id?.trim() ?? "";
  const name = query.name?.trim() ?? "";
  if (!id && !name) return null;

  if (id) {
    const byId = players.find((entry) => entry.id === id);
    if (byId) return byId;
  }

  if (!name) return null;

  const normalized = name.toLowerCase();
  const byName = players.filter((entry) => entry.name.toLowerCase() === normalized);
  if (byName.length === 1) return byName[0];
  return null;
}
