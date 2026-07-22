import { describe, expect, it } from "vite-plus/test";
import {
  buildStandingsPreview,
  preferLeagueEntry,
} from "../lib/homeStandingsPreview";
import type { TableData } from "../lib/datatable/types";

const sampleStandings: TableData = {
  columns: [
    {
      columns: [
        { field: "rank", title: "Platz" },
        { field: "team", title: "Mannschaft" },
        { field: "points", title: "Punkte" },
      ],
    },
  ],
  data: [
    { rank: 1, team: "Team A", points: 10 },
    { rank: 2, team: "Team B", points: 8 },
    { rank: "", team: "", points: "" },
  ],
};

describe("homeStandingsPreview", () => {
  it("builds a compact table snippet", () => {
    const preview = buildStandingsPreview(sampleStandings, {
      league: "BayL",
      leagueLong: "Bayernliga",
      week: 3,
    });
    expect(preview).not.toBeNull();
    expect(preview?.headers).toEqual(["Platz", "Mannschaft", "Punkte"]);
    expect(preview?.rows).toHaveLength(2);
    expect(preview?.rows[0].cells).toEqual(["1", "Team A", "10"]);
  });

  it("prefers BayL when available", () => {
    const leagues = [{ league: "BZOL" }, { league: "BayL" }];
    expect(preferLeagueEntry(leagues)?.league).toBe("BayL");
    expect(preferLeagueEntry([{ league: "Other" }])?.league).toBe("Other");
  });
});

describe("homePalette", () => {
  it("maps topics to rainbowPastel slots 1–7", async () => {
    const { HOME_TOPIC_PALETTE, homePaletteColor } = await import("../lib/homePalette");
    expect(HOME_TOPIC_PALETTE.player).toBe(0);
    expect(HOME_TOPIC_PALETTE.club).toBe(1);
    expect(HOME_TOPIC_PALETTE.league).toBe(2);
    expect(HOME_TOPIC_PALETTE.tournament).toBe(3);
    expect(HOME_TOPIC_PALETTE.clubpokal).toBe(4);
    expect(HOME_TOPIC_PALETTE.club300).toBe(5);
    expect(HOME_TOPIC_PALETTE.myClub).toBe(5);
    expect(HOME_TOPIC_PALETTE.glossary).toBe(6);
    expect(homePaletteColor(HOME_TOPIC_PALETTE.glossary)).toBe("#D95A6A");
  });
});

describe("homeContent", () => {
  it("exports glossary entries", async () => {
    const { GLOSSARY_ENTRIES, HOME_HERO } = await import("../lib/homeContent");
    expect(GLOSSARY_ENTRIES.length).toBeGreaterThan(3);
    expect(HOME_HERO.headline).toContain("Bayern");
  });
});
