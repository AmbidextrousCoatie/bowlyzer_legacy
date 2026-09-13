import { seasonForUrlQuery } from "./api";
import { findEinstiegStory, type EinstiegStory } from "./einstiegStories";
import { MY_CLUB_QUERY_KEY } from "./myClub";
import { linkForPath } from "./navigationQuery";
import { normalizeUnicodeLabel } from "./teamUtils";

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
  // `/turnier` strips non-tournament ?database= — omit it so StoryChrome does not
  // briefly treat the beat as off-path during that rewrite.
  const onTurnier = beat.path === "/turnier" || beat.path.startsWith("/turnier/");
  const database = onTurnier ? null : (beat.params.database ?? source.get("database"));
  if (database) next.set("database", database);
  const myClub = beat.params[MY_CLUB_QUERY_KEY] ?? source.get(MY_CLUB_QUERY_KEY);
  if (myClub) next.set(MY_CLUB_QUERY_KEY, myClub);
  applyBeatParams(next, beat.params);
  if (onTurnier) next.delete("database");
  next.set(STORY_QUERY_KEY, story.id);
  next.set(STORY_BEAT_QUERY_KEY, String(beatIndex + 1));
  const qs = next.toString();
  return qs ? `${beat.path}?${qs}` : beat.path;
}

export function hrefEinstiegIndex(source: URLSearchParams): string {
  return linkForPath("/einstieg", stripStoryQuery(source));
}

/** Params that identify a beat on a path (not ambient globals the page may rewrite). */
const STORY_BEAT_IDENTITY_SKIP_KEYS = new Set(["database"]);

export function isOnStoryBeatPath(
  pathname: string,
  story: EinstiegStory,
  beatIndex: number,
  searchParams?: URLSearchParams,
): boolean {
  const beat = story.beats[beatIndex];
  if (!beat || pathname !== beat.path) return false;
  if (!searchParams) return true;
  for (const [key, value] of Object.entries(beat.params)) {
    if (!value || STORY_BEAT_IDENTITY_SKIP_KEYS.has(key)) continue;
    const expected = key === "season" ? seasonForUrlQuery(value) : value;
    const actual = searchParams.get(key);
    if (actual == null) return false;
    if (normalizeUnicodeLabel(actual) !== normalizeUnicodeLabel(expected)) return false;
  }
  return true;
}
