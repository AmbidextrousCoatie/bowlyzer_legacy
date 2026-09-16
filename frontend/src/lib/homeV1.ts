import type { HomeStats, LatestEvent } from "../hooks/useHome";
import { fetchV1 } from "./v1";

export const HOME_EVENT_LIMIT = 8;

type Dict = Record<string, unknown>;

function asRecord(value: unknown): Dict {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Dict) : {};
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asStr(value: unknown): string {
  if (value == null) return "";
  return String(value).trim();
}

function asNum(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

export function statsFromV1(raw: unknown): HomeStats {
  const counts = asRecord(asRecord(raw).counts);
  return {
    games: asNum(counts.games) ?? 0,
    league_games: asNum(counts.league_games) ?? 0,
    tournament_games: asNum(counts.tournament_games) ?? 0,
    years: asNum(counts.years) ?? asNum(counts.seasons) ?? 0,
    league_seasons: asNum(counts.league_seasons) ?? 0,
    tournaments: asNum(counts.tournaments) ?? 0,
    players: asNum(counts.players) ?? 0,
  };
}

export function latestEventsFromV1(raw: unknown): LatestEvent[] {
  return asList(asRecord(raw).latest_events)
    .map((item) => {
      const row = asRecord(item);
      const weekNum = asNum(row.week ?? row.Week);
      return {
        Season: asStr(row.season || row.Season),
        League: asStr(row.league || row.League),
        Week: weekNum ?? asStr(row.week ?? row.Week),
        Date: asStr(row.date || row.Date),
      };
    })
    .filter((event) => event.Season && event.League);
}

export async function loadHome(limit = HOME_EVENT_LIMIT): Promise<unknown> {
  return fetchV1("/api/v1/home", { limit });
}
