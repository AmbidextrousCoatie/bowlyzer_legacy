export function formatCompetitionLabel(
  name: string,
  options?: {
    isTournament?: boolean;
    tournamentAbbreviations?: Record<string, string>;
  },
): string {
  const label = String(name ?? "").trim();
  if (!label) return "—";
  if (!options?.isTournament) return label;
  return options.tournamentAbbreviations?.[label] ?? label;
}
