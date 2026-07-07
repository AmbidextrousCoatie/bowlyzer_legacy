import { seasonForUrlQuery } from "./api";

export function buildTournamentEventPath(season: string, tournament: string): string {
  const qs = new URLSearchParams();
  qs.set("season", seasonForUrlQuery(season));
  qs.set("tournament", tournament);
  return `/turnier?${qs.toString()}`;
}

export function buildTournamentPlayerEventPath(
  season: string,
  tournament: string,
  player: string,
): string {
  const qs = new URLSearchParams();
  qs.set("season", seasonForUrlQuery(season));
  qs.set("tournament", tournament);
  qs.set("player", player);
  return `/turnier?${qs.toString()}`;
}
