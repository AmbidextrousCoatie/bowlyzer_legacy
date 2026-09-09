import { describe, expect, test } from "vite-plus/test";
import { EINSTIEG_STORIES, findEinstiegStory } from "./einstiegStories";
import {
  hrefEinstiegIndex,
  hrefForStoryBeat,
  parseStoryQuery,
  stripStoryQuery,
} from "./storyQuery";

describe("einstieg stories", () => {
  test("has seven unique story ids", () => {
    const ids = EINSTIEG_STORIES.map((story) => story.id);
    expect(ids).toHaveLength(7);
    expect(new Set(ids).size).toBe(7);
  });

  test("every beat has a path, caption, and pinned database", () => {
    for (const story of EINSTIEG_STORIES) {
      expect(story.beats.length).toBeGreaterThan(0);
      for (const beat of story.beats) {
        expect(beat.path.startsWith("/")).toBe(true);
        expect(beat.caption.length).toBeGreaterThan(20);
        expect(beat.params.database).toBe("db_real_merged");
      }
    }
  });

  test("findEinstiegStory resolves known ids", () => {
    expect(findEinstiegStory("bayernliga")?.persona).toContain("Geschichte");
    expect(findEinstiegStory("missing")).toBeNull();
  });

  test("spieler and tabelle add a season drill-down beat", () => {
    expect(findEinstiegStory("spieler")?.beats).toHaveLength(2);
    expect(findEinstiegStory("spieler")?.beats[1]?.params.season).toBe("25/26");
    expect(findEinstiegStory("tabelle")?.beats).toHaveLength(2);
    expect(findEinstiegStory("tabelle")?.beats[1]?.params.league).toBe("BayL");
  });

  test("club beat 2 is season on overview, beat 3 is Mein Club ligen, beat 4 is team 1", () => {
    const club = findEinstiegStory("club");
    expect(club?.beats).toHaveLength(4);
    expect(club?.beats[1]?.params.season).toBe("25/26");
    expect(club?.beats[1]?.params.team).toBeUndefined();
    expect(club?.beats[2]?.path).toBe("/liga");
    expect(club?.beats[2]?.params.myClub).toBe("BC EMAX Unterföhring");
    expect(club?.beats[2]?.params.season).toBe("25/26");
    expect(club?.beats[2]?.params.league).toBeUndefined();
    expect(club?.beats[3]?.params.team).toBe("BC EMAX Unterföhring 1");
    expect(club?.beats[3]?.params.season).toBe("25/26");
  });

  test("spieltag is one filter cascade", () => {
    const story = findEinstiegStory("spieltag");
    expect(story?.beats).toHaveLength(5);
    expect(story?.beats[0]?.params).toEqual(expect.objectContaining({ season: "25/26" }));
    expect(story?.beats[0]?.params.league).toBeUndefined();
    expect(story?.beats[1]?.params.league).toBe("BayL");
    expect(story?.beats[2]?.params.week).toBe("2");
    expect(story?.beats[3]?.params.team).toBe("BK München 3");
    expect(story?.beats[4]?.params.round).toBe("1");
  });

  test("meisterschaft starts from the full archive then stays on BM Frauen", () => {
    const story = findEinstiegStory("meisterschaft");
    expect(story?.beats[0]?.params.season).toBeUndefined();
    expect(story?.beats[0]?.params.tournament).toBeUndefined();
    for (const beat of story?.beats.slice(1) ?? []) {
      expect(beat.params.tournament).toBe("Bayerische Meisterschaft - Frauen Einzel");
      expect(beat.params.season).toBe("25/26");
    }
  });
});

describe("storyQuery", () => {
  test("parseStoryQuery accepts 1-based beat indexes", () => {
    const parsed = parseStoryQuery(new URLSearchParams("story=club&beat=2"));
    expect(parsed?.story.id).toBe("club");
    expect(parsed?.beatIndex).toBe(1);
  });

  test("parseStoryQuery rejects out-of-range beats", () => {
    expect(parseStoryQuery(new URLSearchParams("story=spieler&beat=9"))).toBeNull();
    expect(parseStoryQuery(new URLSearchParams("story=nope&beat=1"))).toBeNull();
  });

  test("hrefForStoryBeat does not leak previous liga filters", () => {
    const source = new URLSearchParams(
      "database=db_other&myClub=Donaubowler+Regensburg&season=22%2F23&league=BZOL+S1&week=3",
    );
    const story = findEinstiegStory("bayernliga");
    expect(story).not.toBeNull();
    const href = hrefForStoryBeat(story!, 0, source);
    const qs = new URLSearchParams(href.split("?")[1] ?? "");
    expect(href.startsWith("/liga?")).toBe(true);
    expect(qs.get("season")).toBe("all");
    expect(qs.get("league")).toBe("BayL");
    expect(qs.has("week")).toBe(false);
    expect(qs.get("story")).toBe("bayernliga");
    expect(qs.get("beat")).toBe("1");
    expect(qs.get("database")).toBe("db_real_merged");
    expect(qs.get("myClub")).toBe("Donaubowler Regensburg");
  });

  test("hrefForStoryBeat club overview beat drops team", () => {
    const source = new URLSearchParams("team=BC+EMAX+Unterföhring+1&club=BC+EMAX+Unterföhring");
    const story = findEinstiegStory("club");
    expect(story).not.toBeNull();
    const href = hrefForStoryBeat(story!, 1, source);
    const qs = new URLSearchParams(href.split("?")[1] ?? "");
    expect(qs.get("season")).toBe("25/26");
    expect(qs.has("team")).toBe(false);
    expect(qs.get("club")).toBe("BC EMAX Unterföhring");
  });

  test("hrefForStoryBeat club Mein Club liga beat pins myClub and drops league", () => {
    const source = new URLSearchParams(
      "database=db_other&league=BayL&week=2&myClub=Donaubowler+Regensburg",
    );
    const story = findEinstiegStory("club");
    expect(story).not.toBeNull();
    const href = hrefForStoryBeat(story!, 2, source);
    const qs = new URLSearchParams(href.split("?")[1] ?? "");
    expect(href.startsWith("/liga?")).toBe(true);
    expect(qs.get("season")).toBe("25/26");
    expect(qs.get("myClub")).toBe("BC EMAX Unterföhring");
    expect(qs.has("league")).toBe(false);
    expect(qs.has("week")).toBe(false);
    expect(qs.get("story")).toBe("club");
    expect(qs.get("beat")).toBe("3");
  });

  test("stripStoryQuery keeps myClub", () => {
    const next = stripStoryQuery(
      new URLSearchParams("story=spieler&beat=1&myClub=Test&database=db_real_merged"),
    );
    expect(next.get("story")).toBeNull();
    expect(next.get("beat")).toBeNull();
    expect(next.get("myClub")).toBe("Test");
  });

  test("hrefEinstiegIndex drops story keys", () => {
    const href = hrefEinstiegIndex(
      new URLSearchParams("story=spieler&beat=1&myClub=Test&database=db_real_merged"),
    );
    const qs = new URLSearchParams(href.split("?")[1] ?? "");
    expect(href.startsWith("/einstieg")).toBe(true);
    expect(qs.get("story")).toBeNull();
    expect(qs.get("beat")).toBeNull();
    expect(qs.get("myClub")).toBe("Test");
  });
});
