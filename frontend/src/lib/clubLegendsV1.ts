import type { ClubLegendEntry, ClubLegendsPayload } from "../hooks/useLeague";
import { fetchV1 } from "./v1";

type RawLegendEntry = Partial<ClubLegendEntry> & { player?: string };

function legendEntry(raw: RawLegendEntry): ClubLegendEntry {
  return {
    player_id: String(raw.player_id ?? ""),
    player_name: String(raw.player_name ?? raw.player ?? ""),
    value: Number(raw.value ?? 0),
    games: raw.games,
    average: raw.average,
    season: raw.season,
    teams: raw.teams,
    leagues: raw.leagues,
  };
}

function legendList(rows: RawLegendEntry[] | undefined): ClubLegendEntry[] {
  return (rows ?? []).map(legendEntry).filter((row) => row.player_name);
}

/** Map v1 club legends onto the payload ClubLegends already renders. */
export function clubLegendsFromV1(raw: Record<string, unknown>): ClubLegendsPayload {
  return {
    club: String(raw.club ?? ""),
    most_seasons: legendList(raw.most_seasons as RawLegendEntry[] | undefined),
    most_games: legendList(raw.most_games as RawLegendEntry[] | undefined),
    highest_average: legendList(raw.highest_average as RawLegendEntry[] | undefined),
    best_seasons: legendList(raw.best_seasons as RawLegendEntry[] | undefined),
    most_teams_represented: legendList(raw.most_teams_represented as RawLegendEntry[] | undefined),
    most_leagues_seen: legendList(raw.most_leagues_seen as RawLegendEntry[] | undefined),
  };
}

export async function loadClubLegends(
  club: string,
  season?: string | null,
): Promise<ClubLegendsPayload> {
  const raw = await fetchV1<Record<string, unknown>>("/api/v1/clubs/legends", {
    club,
    season: season || undefined,
  });
  return clubLegendsFromV1(raw);
}
