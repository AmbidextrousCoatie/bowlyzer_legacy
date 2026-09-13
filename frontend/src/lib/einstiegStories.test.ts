import { describe, expect, test } from "vite-plus/test";
import { EINSTIEG_STORIES, findEinstiegStory } from "./einstiegStories";
import {
  hrefEinstiegIndex,
  hrefForStoryBeat,
  isOnStoryBeatPath,
  parseStoryQuery,
  stripStoryQuery,
} from "./storyQuery";
import { findVerbandSlide } from "./verbandPresentation";
import { searchParamsForPath } from "./navigationQuery";

describe("einstieg stories", () => {
  test("has unique story ids including verband", () => {
    const ids = EINSTIEG_STORIES.map((story) => story.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toContain("verband");
    expect(ids).toHaveLength(7);
  });

  test("every beat has a path, caption, and pinned database", () => {
    for (const story of EINSTIEG_STORIES) {
      expect(story.beats.length).toBeGreaterThan(0);
      for (const beat of story.beats) {
        expect(beat.path.startsWith("/")).toBe(true);
        expect(beat.caption.length).toBeGreaterThan(10);
        expect(beat.params.database).toBe("db_real_merged");
      }
    }
  });

  test("findEinstiegStory resolves known ids", () => {
    expect(findEinstiegStory("verband")?.persona).toContain("Verbandstag");
    expect(findEinstiegStory("verband")?.topicKey).toBe("verband");
    expect(findEinstiegStory("missing")).toBeNull();
  });

  test("verband rundgang mixes presentation slides and live pages", () => {
    const story = findEinstiegStory("verband");
    expect(story?.beats.length).toBeGreaterThanOrEqual(17);
    expect(story?.beats[0]?.params.slide).toBe("intro");
    expect(story?.beats[1]?.params.slide).toBe("q-300");
    expect(story?.beats[2]?.path).toBe("/club-300");
    const final1 = story?.beats.find((b) => b.params.slide === "final_remarks");
    const final2 = story?.beats.find((b) => b.params.slide === "final_remarks_2");
    expect(final1?.path).toBe("/praesentation");
    expect(final2?.path).toBe("/praesentation");
    expect(findVerbandSlide("final_remarks")?.title).toMatch(/heute/);
    expect(findVerbandSlide("final_remarks_2")?.title).toMatch(/geplant/);
  });

  test("spieler story has career then season then tournament beat", () => {
    const story = findEinstiegStory("spieler");
    expect(story?.beats).toHaveLength(3);
    expect(story?.beats[1]?.params.season).toBe("25/26");
    expect(story?.beats[2]?.path).toBe("/turnier");
  });

  test("tabelle covers history season and promotion race", () => {
    const story = findEinstiegStory("tabelle");
    expect(story?.beats.length).toBeGreaterThanOrEqual(3);
    expect(story?.beats[2]?.params.league).toBe("BayL");
  });

  test("club beat cascade keeps Mein Club liga step", () => {
    const club = findEinstiegStory("club");
    expect(club?.beats).toHaveLength(5);
    expect(club?.beats[3]?.path).toBe("/liga");
    expect(club?.beats[3]?.params.myClub).toBe("BC EMAX Unterföhring");
    expect(club?.beats[3]?.params.season).toBe("17/18");
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

describe("verband presentation slides", () => {
  test("resolves known slides and rejects unknown", () => {
    expect(findVerbandSlide("intro")?.title).toMatch(/Datenerfassung/);
    expect(findVerbandSlide("q-300")?.layout).toBe("question");
    expect(findVerbandSlide("q-300")?.question).toMatch(/300er/);
    expect(findVerbandSlide("excel-liga")?.imageSrc).toContain("excel-liga");
    expect(findVerbandSlide("final_remarks")?.id).toBe("final_remarks");
    expect(findVerbandSlide("final_remarks_2")?.id).toBe("final_remarks_2");
    expect(findVerbandSlide("last_remarks")).toBeNull();
    expect(findVerbandSlide("hooks")).toBeNull();
    expect(findVerbandSlide("nope")).toBeNull();
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

  test("hrefForStoryBeat pins verband presentation slide", () => {
    const story = findEinstiegStory("verband");
    expect(story).not.toBeNull();
    const excelIdx = story!.beats.findIndex((b) => b.params.slide === "excel-liga");
    expect(excelIdx).toBeGreaterThanOrEqual(0);
    const href = hrefForStoryBeat(story!, excelIdx, new URLSearchParams("database=db_other"));
    const qs = new URLSearchParams(href.split("?")[1] ?? "");
    expect(href.startsWith("/praesentation?")).toBe(true);
    expect(qs.get("slide")).toBe("excel-liga");
    expect(qs.get("story")).toBe("verband");
    expect(qs.get("beat")).toBe(String(excelIdx + 1));
    expect(qs.get("database")).toBe("db_real_merged");
  });

  test("isOnStoryBeatPath checks slide param on presentation beats", () => {
    const story = findEinstiegStory("verband");
    expect(story).not.toBeNull();
    const onIntro = new URLSearchParams("slide=intro&database=db_real_merged");
    const onHooks = new URLSearchParams("slide=hooks&database=db_real_merged");
    expect(isOnStoryBeatPath("/praesentation", story!, 0, onIntro)).toBe(true);
    expect(isOnStoryBeatPath("/praesentation", story!, 0, onHooks)).toBe(false);
  });

  test("isOnStoryBeatPath ignores database stripped on /turnier", () => {
    const story = findEinstiegStory("verband");
    expect(story).not.toBeNull();
    const turnierIdx = story!.beats.findIndex(
      (b) => b.path === "/turnier" && b.params.tournament === "Bayerische Meisterschaft Einzel",
    );
    expect(turnierIdx).toBeGreaterThanOrEqual(0);
    const withoutDb = new URLSearchParams(
      `tournament=Bayerische+Meisterschaft+Einzel&story=verband&beat=${turnierIdx + 1}`,
    );
    expect(isOnStoryBeatPath("/turnier", story!, turnierIdx, withoutDb)).toBe(true);
    expect(
      isOnStoryBeatPath(
        "/turnier",
        story!,
        turnierIdx,
        new URLSearchParams(`tournament=Andere&story=verband&beat=${turnierIdx + 1}`),
      ),
    ).toBe(false);
  });

  test("hrefForStoryBeat omits database on /turnier beats", () => {
    const story = findEinstiegStory("verband");
    expect(story).not.toBeNull();
    const turnierIdx = story!.beats.findIndex(
      (b) => b.path === "/turnier" && b.params.tournament === "Bayerische Meisterschaft Einzel",
    );
    expect(turnierIdx).toBeGreaterThanOrEqual(0);
    const href = hrefForStoryBeat(story!, turnierIdx, new URLSearchParams("database=db_real_merged"));
    const qs = new URLSearchParams(href.split("?")[1] ?? "");
    expect(href.startsWith("/turnier?")).toBe(true);
    expect(qs.get("tournament")).toBe("Bayerische Meisterschaft Einzel");
    expect(qs.has("database")).toBe(false);
    expect(qs.get("story")).toBe("verband");
    expect(qs.get("beat")).toBe(String(turnierIdx + 1));
  });

  test("hrefForStoryBeat club overview beat drops team", () => {
    const source = new URLSearchParams("team=BC+EMAX+Unterföhring+1&club=BC+EMAX+Unterföhring");
    const story = findEinstiegStory("club");
    expect(story).not.toBeNull();
    const href = hrefForStoryBeat(story!, 2, source);
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
    const href = hrefForStoryBeat(story!, 3, source);
    const qs = new URLSearchParams(href.split("?")[1] ?? "");
    expect(href.startsWith("/liga?")).toBe(true);
    expect(qs.get("season")).toBe("17/18");
    expect(qs.get("myClub")).toBe("BC EMAX Unterföhring");
    expect(qs.has("league")).toBe(false);
    expect(qs.has("week")).toBe(false);
    expect(qs.get("story")).toBe("club");
    expect(qs.get("beat")).toBe("4");
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

  test("searchParamsForPath strips slide off presentation", () => {
    const source = new URLSearchParams("slide=intro&database=db_real_merged&story=verband&beat=1");
    const next = searchParamsForPath("/liga", source);
    expect(next.has("slide")).toBe(false);
    expect(next.get("story")).toBe("verband");
    expect(next.get("beat")).toBe("1");
  });
});
