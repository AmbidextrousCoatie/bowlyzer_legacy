export type TeamNavParams = {
  club?: string | null;
  team?: string | null;
  season?: string | null;
};

/** Build `/mannschaft` path with club / team / season query params. */
export function buildTeamNavPath(params: TeamNavParams): string {
  const q = new URLSearchParams();
  if (params.club) q.set("club", params.club);
  if (params.team) q.set("team", params.team);
  if (params.season && params.season !== "all") q.set("season", params.season);
  const s = q.toString();
  return s ? `/mannschaft?${s}` : "/mannschaft";
}
