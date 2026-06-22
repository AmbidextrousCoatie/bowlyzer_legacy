/** End-year suffix from German season labels like ``25/26`` → ``26``. */
export function seasonShortSuffix(season: string | number | null | undefined): string {
  const text = String(season ?? "").trim();
  const match = text.match(/^(\d{2})\/(\d{2})$/);
  if (match) return match[2];
  return text.length >= 2 ? text.slice(-2) : text;
}

export function formatCompetitionWithSeason(
  competition: string,
  season: string | number | null | undefined,
): string {
  const comp = String(competition ?? "").trim();
  const suffix = seasonShortSuffix(season);
  if (!comp) return suffix || "—";
  if (!suffix) return comp;
  return `${comp} ${suffix}`;
}

export function formatPeriodDetail(
  row: {
    period_kind?: string | null;
    period_value?: string | null;
    period_number?: number | null;
  },
  t: (key: string, fallback?: string) => string,
): string {
  if (row.period_kind === "week") {
    const week = row.period_number ?? row.period_value ?? "";
    return t("ui.player.period_week", "Spieltag {n}").replace("{n}", String(week));
  }
  const round = String(row.period_value ?? "").trim();
  if (round) return round;
  if (row.period_number != null) {
    return t("ui.player.period_round", "Runde {n}").replace("{n}", String(row.period_number));
  }
  return "—";
}
