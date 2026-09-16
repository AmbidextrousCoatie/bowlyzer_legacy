import type { ClubRankingEntry, ClubRankingsPayload } from "../hooks/useLeague";
import { fetchV1 } from "./v1";

function optStr(value: unknown): string | undefined {
  if (value == null || value === "") return undefined;
  return String(value);
}

function rankingEntry(raw: Record<string, unknown>): ClubRankingEntry {
  const matchTotal = raw.match_total;
  return {
    club: String(raw.club ?? ""),
    value: Number(raw.value ?? 0),
    team: optStr(raw.team),
    season: optStr(raw.season),
    league: optStr(raw.league),
    week: optStr(raw.week),
    round: optStr(raw.round),
    match_total: matchTotal == null || matchTotal === "" ? undefined : Number(matchTotal),
  };
}

function rankingList(rows: unknown): ClubRankingEntry[] {
  if (!Array.isArray(rows)) return [];
  return rows
    .filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object")
    .map((row) => rankingEntry(row))
    .filter((row) => row.club);
}

/** Map v1 club rankings onto the payload ClubRankingsOverview already renders. */
export function clubRankingsFromV1(raw: Record<string, unknown>): ClubRankingsPayload {
  return {
    top_n: Number(raw.top_n ?? 5) || 5,
    highest_total_pinfall: rankingList(raw.highest_total_pinfall),
    most_members: rankingList(raw.most_members),
    highest_weekly_team_average: rankingList(raw.highest_weekly_team_average),
    highest_team_game_average: rankingList(raw.highest_team_game_average),
    most_tournament_wins: rankingList(raw.most_tournament_wins),
    most_league_wins: rankingList(raw.most_league_wins),
  };
}

export async function loadClubRankings(): Promise<ClubRankingsPayload> {
  const raw = await fetchV1<Record<string, unknown>>("/api/v1/clubs/rankings");
  return clubRankingsFromV1(raw);
}
