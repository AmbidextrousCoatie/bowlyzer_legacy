import { getPaletteColor } from "./color-utils";
import {
  tournamentGroupAbbreviation,
  tournamentGroupColorTier,
  type TournamentGroupColorTier,
} from "./tournamentGroupName";

const TIER_SORT_ORDER: Record<TournamentGroupColorTier, number> = {
  bm: 0,
  nbm_sbm: 1,
  other: 2,
};

export function tournamentGroupSortKey(groupName: string, label: string): string {
  const tier = tournamentGroupColorTier(groupName);
  return `${TIER_SORT_ORDER[tier]}|${label}`;
}

export function assignTournamentGroupColors(groups: string[]): Map<string, string> {
  const colors = new Map<string, string>();
  let otherIndex = 0;

  for (const group of groups) {
    const tier = tournamentGroupColorTier(group);
    let paletteIndex: number;
    if (tier === "bm") {
      paletteIndex = 0;
    } else if (tier === "nbm_sbm") {
      paletteIndex = 1;
    } else {
      paletteIndex = 2 + otherIndex;
      otherIndex += 1;
    }
    colors.set(group, getPaletteColor(paletteIndex));
  }

  return colors;
}

export function sortTournamentGroupNames(groupNames: string[]): string[] {
  return [...groupNames].sort((a, b) => {
    const labelA = tournamentGroupAbbreviation(a) ?? a;
    const labelB = tournamentGroupAbbreviation(b) ?? b;
    return tournamentGroupSortKey(a, labelA).localeCompare(tournamentGroupSortKey(b, labelB));
  });
}

export function formatTournamentAverage(average: number | null | undefined): string | null {
  if (average == null || !Number.isFinite(average)) return null;
  return average.toFixed(1);
}
