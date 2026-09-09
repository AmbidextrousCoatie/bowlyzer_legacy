import type { LeagueOption } from "../hooks/useLeague";
import {
  getLeagueLevel,
  getLeagueLevelLongLabel,
  isKnownLeagueLevel,
  isLeagueRegion,
  leagueInRegionScope,
  sortLeaguesByLevel,
  type LeagueRegion,
} from "./leagueLevel";

export type LeagueSelectGroup = {
  level: number;
  label: string;
  leagues: LeagueOption[];
};

export type ParsedLeagueSelect = {
  league: string;
  division: string;
  level: number | null;
};

const LEAGUE_LEVEL_SELECT_PREFIX = "level:";

export function leagueLevelSelectValue(level: number): string {
  return `${LEAGUE_LEVEL_SELECT_PREFIX}${level}`;
}

export function parseLeagueLevelParam(value: string): number | null {
  if (!/^\d+$/.test(value)) return null;
  const level = Number(value);
  return isKnownLeagueLevel(level) ? level : null;
}

export function parseLeagueLevelSelectValue(value: string): number | null {
  if (!value.startsWith(LEAGUE_LEVEL_SELECT_PREFIX)) return null;
  return parseLeagueLevelParam(value.slice(LEAGUE_LEVEL_SELECT_PREFIX.length));
}

export function leagueSelectDisplayLabel(
  value: string,
  leagues: LeagueOption[],
  t: (key: string, fallback?: string) => string,
): string {
  if (!value) return t("ui.league.region_all", "Alle");
  if (value === "north") return t("ui.league.region_north", "Norbereich");
  if (value === "south") return t("ui.league.region_south", "Südbereich");
  const level = parseLeagueLevelSelectValue(value);
  if (level != null) return getLeagueLevelLongLabel(level);
  const match = leagues.find((item) => item.value === value);
  return match?.long_name || match?.short_name || value;
}

export function leagueSelectValue(league: string, division: string, level: number | null): string {
  if (league) return league;
  if (level != null) return leagueLevelSelectValue(level);
  if (isLeagueRegion(division)) return division;
  return "";
}

export function parseLeagueSelectValue(value: string): ParsedLeagueSelect {
  if (isLeagueRegion(value)) return { league: "", division: value, level: null };
  if (!value) return { league: "", division: "", level: null };
  if (value.startsWith(LEAGUE_LEVEL_SELECT_PREFIX)) {
    const level = parseLeagueLevelSelectValue(value);
    return { league: "", division: "", level };
  }
  return { league: value, division: "", level: null };
}

export function leaguesForRegionSelect(
  leagues: LeagueOption[],
  league: string,
  division: string,
): LeagueOption[] {
  const region: LeagueRegion | null =
    !league && isLeagueRegion(division) ? division : null;
  const scoped = region
    ? leagues.filter((item) => leagueInRegionScope(item.value, region))
    : leagues;
  return sortLeaguesByLevel(scoped);
}

export function groupLeaguesByLevel(leagues: LeagueOption[]): LeagueSelectGroup[] {
  const byLevel = new Map<number, LeagueOption[]>();
  for (const league of leagues) {
    const level = getLeagueLevel(league.value);
    const list = byLevel.get(level) ?? [];
    list.push(league);
    byLevel.set(level, list);
  }
  return [...byLevel.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([level, items]) => ({
      level,
      label: getLeagueLevelLongLabel(level),
      leagues: items,
    }));
}

export function regionHasLeagues(leagues: LeagueOption[], region: LeagueRegion): boolean {
  return leagues.some((league) => leagueInRegionScope(league.value, region));
}
