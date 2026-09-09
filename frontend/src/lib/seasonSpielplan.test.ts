import { describe, expect, test } from "vite-plus/test";
import type { TableData } from "./datatable/types";
import {
  abbreviateVenues,
  buildSeasonSpielplan,
  buildSpielplanChartModel,
  coerceTimetableTable,
  formatSpielplanDate,
  formatTimetableTable,
  normalizeVenueKey,
  parseSpielplanDateKey,
  parseTimetableEvents,
} from "./seasonSpielplan";

function timetable(rows: unknown[][]): TableData {
  return {
    columns: [
      {
        title: "",
        columns: [
          { field: "week", title: "Spieltag" },
          { field: "date", title: "Datum" },
          { field: "location", title: "Ort" },
          { field: "status", title: "Status" },
        ],
      },
    ],
    data: rows,
  };
}

const blS1 = { value: "BL S1", short_name: "BL S1", long_name: "Bereichsliga Süd 1" };
const klS3 = { value: "KL S3", short_name: "KL S3", long_name: "Kreisliga Süd 3" };
const aN1 = { value: "A N1", short_name: "A N1", long_name: "A-Klasse Nord 1" };

describe("normalizeVenueKey", () => {
  test("treats hyphen and space variants as the same house", () => {
    expect(normalizeVenueKey("Isar-München")).toBe(normalizeVenueKey("Isar München"));
    expect(normalizeVenueKey("City-Augsburg")).toBe(normalizeVenueKey("City Augsburg"));
  });
});

describe("parseSpielplanDateKey", () => {
  test("keeps ISO dates and maps German dates", () => {
    expect(parseSpielplanDateKey("2011-09-18")).toBe("2011-09-18");
    expect(parseSpielplanDateKey("18.09.2011")).toBe("2011-09-18");
  });

  test("drops TBD placeholders", () => {
    expect(parseSpielplanDateKey("TBD")).toBeNull();
    expect(parseSpielplanDateKey("nan")).toBeNull();
    expect(parseSpielplanDateKey("")).toBeNull();
  });
});

describe("formatSpielplanDate", () => {
  test("uses UTC so weekdays do not shift", () => {
    expect(formatSpielplanDate("2011-09-18", "de")).toEqual({
      weekday: "So",
      displayDate: "18.09.2011",
    });
    expect(formatSpielplanDate("2011-09-18", "en")).toEqual({
      weekday: "Sun",
      displayDate: "18.09.2011",
    });
  });
});

describe("parseTimetableEvents", () => {
  test("reads array rows from the Termine payload", () => {
    const events = parseTimetableEvents(
      timetable([[1, "2011-09-18", "Brunnthal", "Completed"]]),
      blS1,
    );
    expect(events).toEqual([
      {
        league: "BL S1",
        leagueShort: "BL S1",
        leagueLong: "Bereichsliga Süd 1",
        week: 1,
        dateKey: "2011-09-18",
        venueRaw: "Brunnthal",
        venueKey: "brunnthal",
      },
    ]);
  });

  test("reads object rows and skips invalid weeks", () => {
    const table: TableData = {
      columns: [{ columns: [{ field: "week" }, { field: "date" }, { field: "location" }] }],
      data: [
        { week: 2, date: "2011-10-02", location: "BluBowl Nürnberg" },
        { week: "x", date: "2011-10-09", location: "Brunnthal" },
      ],
    };
    expect(parseTimetableEvents(table, aN1)).toHaveLength(1);
    expect(parseTimetableEvents(table, aN1)[0]?.week).toBe(2);
  });

  test("recovers rows from a stringified TableData payload", () => {
    const repr =
      "TableData(columns=[], data=[[2, '2011-10-09', 'Cosmos Arena Nürnberg', 'Completed'], [3, '2011-10-23', 'OK Bowling Bindlach', 'Completed']], title='A N1')";
    const events = parseTimetableEvents(repr, aN1);
    expect(events.map((e) => [e.week, e.dateKey, e.venueRaw])).toEqual([
      [2, "2011-10-09", "Cosmos Arena Nürnberg"],
      [3, "2011-10-23", "OK Bowling Bindlach"],
    ]);
    const table = coerceTimetableTable(repr);
    expect(table?.columns[0]?.columns?.map((col) => col.field)).toEqual([
      "week",
      "date",
      "location",
      "status",
    ]);
    expect(table?.data[0]).toEqual([2, "2011-10-09", "Cosmos Arena Nürnberg", "Completed"]);
  });
});

describe("formatTimetableTable", () => {
  test("turns ISO dates into weekday plus German day.month.year", () => {
    const formatted = formatTimetableTable(
      timetable([[1, "2011-09-18", "Brunnthal", "Completed"]]),
      "de",
    );
    expect(formatted?.data[0]).toEqual([1, "So 18.09.2011", "Brunnthal", "Completed"]);
  });
});

describe("buildSeasonSpielplan", () => {
  test("groups by date then venue and flags shared houses", () => {
    const days = buildSeasonSpielplan(
      [blS1, klS3, aN1],
      [
        timetable([
          [1, "2011-09-18", "Brunnthal", "Completed"],
          [2, "2011-10-02", "Dream-Bowl München", "Completed"],
        ]),
        timetable([
          [1, "2011-09-18", "Brunnthal", "Completed"],
          [2, "2011-10-02", "Isar München", "Completed"],
        ]),
        timetable([[1, "2011-09-18", "BluBowl Nürnberg", "Completed"]]),
      ],
    );

    expect(days).toHaveLength(2);
    expect(days[0]).toMatchObject({
      dateKey: "2011-09-18",
      weekday: "So",
      displayDate: "18.09.2011",
      leagueCount: 3,
      venueCount: 2,
    });
    expect(days[0]?.venues.map((v) => v.displayName)).toEqual(["Brunnthal", "BluBowl Nürnberg"]);
    expect(days[0]?.venues[0]).toMatchObject({ shared: true, displayName: "Brunnthal" });
    expect(days[0]?.venues[0]?.events.map((e) => e.leagueShort)).toEqual(["BL S1", "KL S3"]);
    expect(days[0]?.venues[1]?.shared).toBe(false);

    expect(days[1]?.dateKey).toBe("2011-10-02");
    expect(days[1]?.venues[0]?.shared).toBe(false);
  });

  test("merges hyphenated venue names on the same day", () => {
    const days = buildSeasonSpielplan(
      [blS1, klS3],
      [
        timetable([[1, "2011-09-18", "Isar-München", "Completed"]]),
        timetable([[1, "2011-09-18", "Isar München", "Completed"]]),
      ],
    );
    expect(days[0]?.venues).toHaveLength(1);
    expect(days[0]?.venues[0]?.shared).toBe(true);
    expect(days[0]?.venues[0]?.displayName).toMatch(/Isar/);
  });

  test("puts TBD dates in a trailing undated bucket", () => {
    const days = buildSeasonSpielplan(
      [aN1],
      [
        timetable([
          [1, "TBD", "Brunnthal", "Pending"],
          [2, "2011-10-02", "BluBowl Nürnberg", "Completed"],
        ]),
      ],
    );
    expect(days.map((d) => d.dateKey)).toEqual(["2011-10-02", null]);
    expect(days[1]?.venues[0]?.events[0]?.week).toBe(1);
  });
});

describe("abbreviateVenues", () => {
  test("uses camelCase and hyphen tokens for bowling houses", () => {
    const abbrevs = abbreviateVenues([
      { venueKey: "dream bowl munchen", displayName: "Dream-Bowl München" },
      { venueKey: "blubowl nurnberg", displayName: "BluBowl Nürnberg" },
    ]);
    expect(abbrevs.get("dream bowl munchen")).toBe("DBM");
    expect(abbrevs.get("blubowl nurnberg")).toBe("BBN");
  });

  test("disambiguates colliding initials", () => {
    const abbrevs = abbreviateVenues([
      { venueKey: "city augsburg", displayName: "City Augsburg" },
      { venueKey: "cosmos arena", displayName: "Cosmos Arena" },
    ]);
    expect(abbrevs.get("city augsburg")).toBe("CA");
    expect(abbrevs.get("cosmos arena")).not.toBe("CA");
    expect(abbrevs.get("cosmos arena")).toMatch(/^[A-Z0-9]{2,6}$/);
  });
});

describe("buildSpielplanChartModel", () => {
  test("lays out one row per league and colors by venue", () => {
    const palette = ["#111111", "#222222", "#333333"];
    const model = buildSpielplanChartModel(
      [aN1, blS1, klS3],
      [
        timetable([[1, "2011-09-18", "BluBowl Nürnberg", "Completed"]]),
        timetable([
          [1, "2011-09-18", "Brunnthal", "Completed"],
          [2, "2011-10-02", "Dream-Bowl München", "Completed"],
        ]),
        timetable([[1, "2011-09-18", "Brunnthal", "Completed"]]),
      ],
      "de",
      palette,
    );

    expect(model.leagueLabels).toEqual(["BL S1", "KL S3", "A N1"]);
    expect(model.dateKeys).toEqual(["2011-09-18", "2011-10-02"]);
    expect(model.dateLabels).toEqual(["So 18.09", "So 02.10"]);

    const dream = model.venues.find((venue) => venue.displayName === "Dream-Bowl München");
    expect(dream?.abbrev).toBe("DBM");
    const blubowl = model.venues.find((venue) => venue.displayName === "BluBowl Nürnberg");
    expect(blubowl?.abbrev).toBe("BBN");

    const sharedColor = model.points.find(
      (point) => point.league === "BL S1" && point.dateKey === "2011-09-18",
    )?.color;
    expect(
      model.points.find((point) => point.league === "KL S3" && point.dateKey === "2011-09-18")
        ?.color,
    ).toBe(sharedColor);

    expect(model.eventsByDate["2011-09-18"]?.map((event) => event.leagueShort)).toEqual([
      "A N1",
      "BL S1",
      "KL S3",
    ]);
  });

  test("keeps undated matchdays off the grid", () => {
    const model = buildSpielplanChartModel(
      [aN1],
      [
        timetable([
          [1, "TBD", "Brunnthal", "Pending"],
          [2, "2011-10-02", "BluBowl Nürnberg", "Completed"],
        ]),
      ],
      "de",
      ["#1B8CA6"],
    );
    expect(model.points).toHaveLength(1);
    expect(model.undated).toHaveLength(1);
    expect(model.undated[0]?.week).toBe(1);
  });
});
