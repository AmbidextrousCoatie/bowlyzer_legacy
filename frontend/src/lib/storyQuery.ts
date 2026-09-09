import { seasonForUrlQuery } from "./api";
import { findEinstiegStory, type EinstiegStory } from "./einstiegStories";
import { MY_CLUB_QUERY_KEY } from "./myClub";
import { linkForPath } from "./navigationQuery";

export const STORY_QUERY_KEY = "story";
export const STORY_BEAT_QUERY_KEY = "beat";

export type ParsedStoryQuery = {
  story: EinstiegStory;
  beatIndex: number;
};

export function parseStoryQuery(params: URLSearchParams): ParsedStoryQuery | null {
  const story = findEinstiegStory(params.get(STORY_QUERY_KEY));
  if (!story) return null;
  const rawBeat = Number.parseInt(params.get(STORY_BEAT_QUERY_KEY) ?? "", 10);
  const beatIndex = Number.isFinite(rawBeat) ? rawBeat - 1 : 0;
  if (beatIndex < 0 || beatIndex >= story.beats.length) return null;
  return { story, beatIndex };
}

export function stripStoryQuery(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params);
  next.delete(STORY_QUERY_KEY);
  next.delete(STORY_BEAT_QUERY_KEY);
  return next;
}

function applyBeatParams(target: URLSearchParams, params: Record<string, string>): void {
  for (const [key, value] of Object.entries(params)) {
    if (!value) continue;
    target.set(key, key === "season" ? seasonForUrlQuery(value) : value);
  }
}

/** Build a beat URL from global params only (database, myClub) plus the beat’s own keys. */
export function hrefForStoryBeat(
  story: EinstiegStory,
  beatIndex: number,
  source: URLSearchParams,
): string {
  const beat = story.beats[beatIndex];
  if (!beat) return "/einstieg";

  const next = new URLSearchParams();
  const database = beat.params.database ?? source.get("database");
  if (database) next.set("database", database);
  const myClub = beat.params[MY_CLUB_QUERY_KEY] ?? source.get(MY_CLUB_QUERY_KEY);
  if (myClub) next.set(MY_CLUB_QUERY_KEY, myClub);
  applyBeatParams(next, beat.params);
  next.set(STORY_QUERY_KEY, story.id);
  next.set(STORY_BEAT_QUERY_KEY, String(beatIndex + 1));
  const qs = next.toString();
  return qs ? `${beat.path}?${qs}` : beat.path;
}

export function hrefEinstiegIndex(source: URLSearchParams): string {
  return linkForPath("/einstieg", stripStoryQuery(source));
}

export function isOnStoryBeatPath(
  pathname: string,
  story: EinstiegStory,
  beatIndex: number,
): boolean {
  const beat = story.beats[beatIndex];
  return !!beat && pathname === beat.path;
}
