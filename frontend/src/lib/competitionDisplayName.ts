import { normalizeTournamentGroupName, tournamentGroupAbbreviation } from "./tournamentGroupName";

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
  const lookup = options.tournamentAbbreviations;
  const direct = lookup?.[label];
  if (direct) return direct;
  const group = normalizeTournamentGroupName(label);
  const grouped = lookup?.[group] ?? tournamentGroupAbbreviation(group);
  if (grouped) return grouped;
  return group;
}
