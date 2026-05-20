import { getPaletteColor } from "./color-utils";

/** NFC normalization so URL / API strings match CSV labels (e.g. ``ö`` as one codepoint vs decomposed). */
export function normalizeUnicodeLabel(text: string): string {
  return String(text ?? "").trim().normalize("NFC");
}

/**
 * Club / team helpers for `/club`.
 *
 * German bowling org (reference): Verein → Club → Team — e.g.
 * BV 68 Regensburg → Donaubowler Regensburg → Mannschaft 1/2/3.
 * Only Club + Team exist in data; Verein is out of scope.
 *
 * Mirrors backend `LeagueService._split_club_and_team_number`.
 */
export function splitClubAndTeamNumber(teamName: string): { club: string; teamNumber: string } {
  const text = String(teamName ?? "").trim();
  if (!text) return { club: "", teamNumber: "" };
  const match = /^(.*?)(?:\s+(\d+))?$/.exec(text);
  if (!match) return { club: text, teamNumber: "" };
  return {
    club: String(match[1] ?? "").trim(),
    teamNumber: String(match[2] ?? "").trim(),
  };
}

export function teamsForClub(allTeams: string[], club: string): string[] {
  const needle = normalizeUnicodeLabel(club);
  if (!needle) return [];
  return allTeams
    .filter((name) => normalizeUnicodeLabel(splitClubAndTeamNumber(name).club) === needle)
    .sort((a, b) => {
      const na = splitClubAndTeamNumber(a).teamNumber;
      const nb = splitClubAndTeamNumber(b).teamNumber;
      if (na && nb) return Number(na) - Number(nb);
      if (na) return -1;
      if (nb) return 1;
      return a.localeCompare(b);
    });
}

export function teamDisplayLabel(teamName: string): string {
  const { teamNumber } = splitClubAndTeamNumber(teamName);
  if (teamNumber) return teamNumber;
  return "Basis";
}

/** Palette index for club teams: Mannschaft 1 → rainbow[0], 2 → [1], … */
export function clubTeamPaletteIndex(teamNumber: string): number {
  if (teamNumber && /^\d+$/.test(teamNumber)) {
    return Math.max(0, parseInt(teamNumber, 10) - 1);
  }
  return 0;
}

/** Stable rainbow color per Mannschaft number within a club. */
export function getClubTeamColor(teamName: string): string {
  const { teamNumber } = splitClubAndTeamNumber(teamName);
  return getPaletteColor(clubTeamPaletteIndex(teamNumber));
}

export function clubTeamFullName(club: string, teamNumber: string): string {
  if (!teamNumber || teamNumber === "base") return club;
  if (/^\d+$/.test(teamNumber)) return `${club} ${teamNumber}`;
  return `${club} ${teamNumber}`;
}
