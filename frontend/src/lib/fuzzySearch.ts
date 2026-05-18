/** Score a single haystack string against a needle (higher = better). */
export function fuzzyScore(needle: string, haystack: string): number {
  if (!needle) return 1;
  if (!haystack) return 0;
  if (haystack === needle) return 1000;
  if (haystack.startsWith(needle)) return 800 - Math.min(haystack.length - needle.length, 50);
  if (haystack.includes(needle)) return 600 - haystack.indexOf(needle);

  const words = haystack.split(/\s+/);
  if (words.some((w) => w.startsWith(needle))) return 520;

  let ni = 0;
  for (let hi = 0; hi < haystack.length && ni < needle.length; hi++) {
    if (haystack[hi] === needle[ni]) ni++;
  }
  if (ni === needle.length) return 400 - (haystack.length - needle.length);

  return 0;
}

export function rankFuzzyStrings(query: string, items: string[], limit = 50): string[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return items.slice(0, limit);

  return items
    .map((item) => ({ item, score: fuzzyScore(needle, item.toLowerCase()) }))
    .filter((row) => row.score > 0)
    .sort((a, b) => b.score - a.score || a.item.localeCompare(b.item))
    .slice(0, limit)
    .map((row) => row.item);
}

/** Fuzzy rank arbitrary items by a string label (e.g. player names). */
export function rankFuzzyBy<T>(
  query: string,
  items: T[],
  getLabel: (item: T) => string,
  limit = 50,
): T[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return items.slice(0, limit);

  return items
    .map((item) => ({
      item,
      score: fuzzyScore(needle, getLabel(item).toLowerCase()),
    }))
    .filter((row) => row.score > 0)
    .sort(
      (a, b) =>
        b.score - a.score || getLabel(a.item).localeCompare(getLabel(b.item)),
    )
    .slice(0, limit)
    .map((row) => row.item);
}
