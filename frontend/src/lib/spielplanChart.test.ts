import { describe, expect, test } from "vite-plus/test";
import {
  SPIELPLAN_PILL_SIZE,
  SPIELPLAN_PILL_SYMBOL,
  spielplanChartHeight,
  spielplanChartOption,
  spielplanPointFromEvent,
} from "./spielplanChart";
import type { SpielplanChartModel } from "./seasonSpielplan";

const model: SpielplanChartModel = {
  leagueLabels: ["BL S1", "A N1"],
  dateKeys: ["2011-09-18", "2011-10-02"],
  dateLabels: ["So 18.09", "So 02.10"],
  venues: [
    {
      venueKey: "dream bowl munchen",
      displayName: "Dream-Bowl München",
      abbrev: "DBM",
      color: "#1B8CA6",
    },
  ],
  points: [
    {
      league: "BL S1",
      leagueShort: "BL S1",
      leagueLong: "Bereichsliga Süd 1",
      week: 1,
      dateKey: "2011-09-18",
      dateLabel: "So 18.09",
      venueKey: "dream bowl munchen",
      venueName: "Dream-Bowl München",
      abbrev: "DBM",
      color: "#1B8CA6",
    },
  ],
  eventsByDate: {
    "2011-09-18": [
      {
        league: "BL S1",
        leagueShort: "BL S1",
        leagueLong: "Bereichsliga Süd 1",
        week: 1,
        dateKey: "2011-09-18",
        venueRaw: "Dream-Bowl München",
        venueKey: "dream bowl munchen",
      },
      {
        league: "A N1",
        leagueShort: "A N1",
        leagueLong: "A-Klasse Nord 1",
        week: 1,
        dateKey: "2011-09-18",
        venueRaw: "BluBowl Nürnberg",
        venueKey: "blubowl nurnberg",
      },
    ],
  },
  undated: [],
};

describe("spielplanChartOption", () => {
  test("plots date keys on x and leagues on y", () => {
    const option = spielplanChartOption(model, (_key, fallback) => fallback ?? _key, "de");
    expect(option?.xAxis).toMatchObject({ type: "category", data: model.dateKeys });
    expect(option?.yAxis).toMatchObject({
      type: "category",
      data: ["BL S1", "A N1"],
      inverse: true,
    });
    const series = Array.isArray(option?.series) ? option.series : [];
    expect(series[0]).toMatchObject({
      type: "scatter",
      symbol: SPIELPLAN_PILL_SYMBOL,
      symbolSize: SPIELPLAN_PILL_SIZE,
    });
    expect(option?.xAxis).toMatchObject({ splitLine: { show: false } });
    expect(option?.yAxis).toMatchObject({ splitLine: { show: false } });
    expect((series[0] as { markLine?: { data: unknown[] } }).markLine?.data).toEqual([
      { xAxis: "2011-09-18" },
      { xAxis: "2011-10-02" },
    ]);
    expect((series[0] as { data: Array<{ value: unknown }> }).data[0]?.value).toEqual([
      "2011-09-18",
      "BL S1",
    ]);
  });

  test("tooltip lists the house and every league that day", () => {
    const option = spielplanChartOption(model, (_key, fallback) => fallback ?? _key, "de");
    expect(option?.tooltip).toBeTruthy();
    const tooltip = option?.tooltip;
    if (!tooltip || typeof tooltip !== "object" || !("formatter" in tooltip)) {
      throw new Error("expected tooltip formatter");
    }
    const formatter = tooltip.formatter as (raw: unknown) => string;
    const html = formatter({ data: model.points[0] });
    expect(html).toContain("So 18.09.2011");
    expect(html).toContain("DBM = Dream-Bowl München");
    expect(html).toContain("Ligen an diesem Tag");
    expect(html).toContain("BL S1");
    expect(html).toContain("A N1");
  });
});

describe("spielplanPointFromEvent", () => {
  test("reads league and week from a scatter payload", () => {
    expect(
      spielplanPointFromEvent({ ...model.points[0], value: ["2011-09-18", "BL S1"] }),
    ).toMatchObject({ league: "BL S1", week: 1 });
    expect(spielplanPointFromEvent({ league: "BL S1" })).toBeNull();
  });
});

describe("spielplanChartHeight", () => {
  test("grows with the league count", () => {
    expect(spielplanChartHeight(2)).toBe(280);
    expect(spielplanChartHeight(20)).toBeGreaterThan(spielplanChartHeight(10));
  });
});

describe("SPIELPLAN_PILL_SIZE", () => {
  test("is one size that fits three letters", () => {
    expect(SPIELPLAN_PILL_SIZE).toEqual([44, 28]);
  });
});
