import { buildUrl } from "./api";
import { CLUB_PATH } from "./navigationQuery";

export type ClubNavParams = {
  club?: string | null;
  team?: string | null;
  season?: string | null;
};

/** @deprecated Use {@link ClubNavParams}. */
export type TeamNavParams = ClubNavParams;

/** Build `/club` path with club / team / season query params. */
export function buildClubNavPath(params: ClubNavParams): string {
  const q: Record<string, string> = {};
  if (params.club) q.club = params.club;
  if (params.team) q.team = params.team;
  if (params.season && params.season !== "all") q.season = params.season;
  return buildUrl(CLUB_PATH, q);
}

/** @deprecated Use {@link buildClubNavPath}. */
export const buildTeamNavPath = buildClubNavPath;
