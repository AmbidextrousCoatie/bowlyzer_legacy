/** Normalize tournament player names for roster matching. */
export function normalizePlayerName(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, " ");
}

/**
 * Resolve a deep-link player string to the canonical name from the tournament roster.
 * Handles minor spelling variants and "First Last" vs "Last, First".
 */
export function resolveTournamentPlayerName(requested: string, roster: string[]): string | null {
  const trimmed = requested.trim();
  if (!trimmed || roster.length === 0) return null;

  const want = normalizePlayerName(trimmed);
  const exact = roster.find((p) => normalizePlayerName(p) === want);
  if (exact) return exact;

  if (trimmed.includes(",")) {
    const [last, ...rest] = trimmed.split(",").map((s) => s.trim());
    const first = rest.join(" ").trim();
    if (first && last) {
      const flipped = `${first} ${last}`;
      const hit = roster.find((p) => normalizePlayerName(p) === normalizePlayerName(flipped));
      if (hit) return hit;
    }
  } else {
    const parts = trimmed.split(/\s+/);
    if (parts.length >= 2) {
      const last = parts[parts.length - 1];
      const first = parts.slice(0, -1).join(" ");
      const flipped = `${last}, ${first}`;
      const hit = roster.find((p) => normalizePlayerName(p) === normalizePlayerName(flipped));
      if (hit) return hit;
    }
  }

  return null;
}
