import type { IndividualGameRecord } from "../hooks/usePlayer";
import { fetchV1 } from "./v1";

function optStr(value: unknown): string | null {
  if (value == null || value === "") return null;
  return String(value);
}

function optNum(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function teamNumber(raw: Record<string, unknown>, teamName: string | null): number | null {
  const explicit = optNum(raw.team_number);
  if (explicit != null) return explicit;
  const match = String(teamName ?? "").match(/ (\d+)$/);
  return match ? Number(match[1]) : null;
}

function gameFromV1(raw: Record<string, unknown>): IndividualGameRecord {
  const teamName = optStr(raw.team_name ?? raw.team);
  const round = raw.round_number != null && raw.round_number !== "" ? raw.round_number : raw.round;
  return {
    player_name: optStr(raw.player_name ?? raw.player),
    player_id: optStr(raw.player_id),
    score: optNum(raw.score),
    date: optStr(raw.date ?? raw.game_date),
    season: optStr(raw.season),
    competition: optStr(raw.competition),
    is_tournament: Boolean(raw.is_tournament),
    club: optStr(raw.club),
    team_name: teamName,
    team_number: teamNumber(raw, teamName),
    week: optNum(raw.week),
    round_number: optNum(round),
  };
}

/** Map v1 honor/300 onto the IndividualGameRecord[] Club 300 already renders. */
export function club300FromV1(raw: Record<string, unknown> | unknown[]): IndividualGameRecord[] {
  const rows = Array.isArray(raw) ? raw : raw.games;
  if (!Array.isArray(rows)) return [];
  return rows
    .filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object")
    .map(gameFromV1)
    .filter((row) => row.player_name);
}

export async function loadClub300Games(club?: string | null): Promise<IndividualGameRecord[]> {
  const raw = await fetchV1<Record<string, unknown>>("/api/v1/honor/300", {
    club: club || undefined,
  });
  return club300FromV1(raw);
}
