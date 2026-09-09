import type { TableData } from "./datatable/types";
import { BRAND_PRIMARY } from "./design-tokens";
import { getLeagueLevel } from "./leagueLevel";

export type SpielplanLeagueMeta = {
  value: string;
  short_name: string;
  long_name: string;
};

export type SpielplanEvent = {
  league: string;
  leagueShort: string;
  leagueLong: string;
  week: number;
  dateKey: string | null;
  venueRaw: string;
  venueKey: string;
};

export type SpielplanVenueGroup = {
  venueKey: string;
  displayName: string;
  shared: boolean;
  events: SpielplanEvent[];
};

export type SpielplanDay = {
  dateKey: string | null;
  weekday: string;
  displayDate: string;
  leagueCount: number;
  venueCount: number;
  venues: SpielplanVenueGroup[];
};

const FALLBACK_FIELDS = ["week", "date", "location", "status"] as const;
const TBD_DATES = new Set(["", "tbd", "nan", "-", "—", "null", "undefined"]);

const WEEKDAY_DE = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"] as const;
const WEEKDAY_EN = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;

function asText(raw: unknown): string {
  if (raw == null) return "";
  if (typeof raw === "string") return raw.trim();
  if (typeof raw === "number" || typeof raw === "boolean") return String(raw);
  return "";
}

export function normalizeVenueKey(raw: string): string {
  return raw
    .normalize("NFC")
    .trim()
    .toLowerCase()
    .replace(/[.\u00a0]/g, " ")
    .replace(/[-–—]/g, " ")
    .replace(/\s+/g, " ");
}

export function parseSpielplanDateKey(raw: unknown): string | null {
  const text = asText(raw);
  if (!text || TBD_DATES.has(text.toLowerCase())) return null;
  const iso = /^(\d{4})-(\d{2})-(\d{2})/.exec(text);
  if (iso) return `${iso[1]}-${iso[2]}-${iso[3]}`;
  const de = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/.exec(text);
  if (de) {
    return `${de[3]}-${de[2].padStart(2, "0")}-${de[1].padStart(2, "0")}`;
  }
  return null;
}

export function formatSpielplanDate(
  dateKey: string,
  language: "de" | "en" = "de",
): { weekday: string; displayDate: string } {
  const iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateKey);
  if (!iso) return { weekday: "", displayDate: dateKey };
  const year = Number(iso[1]);
  const month = Number(iso[2]);
  const day = Number(iso[3]);
  const weekdayIndex = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  const weekday = (language === "en" ? WEEKDAY_EN : WEEKDAY_DE)[weekdayIndex] ?? "";
  return {
    weekday,
    displayDate: `${String(day).padStart(2, "0")}.${String(month).padStart(2, "0")}.${year}`,
  };
}

function columnFields(table: TableData | undefined): string[] {
  const fields: string[] = [];
  for (const group of table?.columns ?? []) {
    for (const col of group.columns ?? []) {
      if (col.field) fields.push(col.field);
    }
  }
  return fields.length > 0 ? fields : [...FALLBACK_FIELDS];
}

function cellValue(
  row: Record<string, unknown> | unknown[],
  fields: string[],
  field: string,
): unknown {
  if (Array.isArray(row)) {
    const idx = fields.indexOf(field);
    return idx >= 0 ? row[idx] : undefined;
  }
  return row[field];
}

function parseWeek(raw: unknown): number | null {
  const n = typeof raw === "number" ? raw : Number(asText(raw));
  if (!Number.isFinite(n) || n <= 0) return null;
  return n;
}

const TIMETABLE_COLUMNS: TableData["columns"] = [
  {
    title: "",
    columns: [
      { field: "week", title: "Spieltag", align: "center" },
      { field: "date", title: "Datum", align: "center" },
      { field: "location", title: "Ort", align: "left" },
      { field: "status", title: "Status", align: "center" },
    ],
  },
];

function unquotePyString(value: string): string {
  return value.replace(/\\'/g, "'");
}

/** Flask used to jsonify TableData via default=str; recover week/date/location rows. */
export function coerceTimetableTable(raw: unknown): TableData | undefined {
  if (!raw) return undefined;
  if (typeof raw === "object") {
    const table = raw as TableData;
    if (Array.isArray(table.data)) return table;
    return undefined;
  }
  if (typeof raw !== "string" || !raw.includes("data=")) return undefined;
  const dataStart = raw.indexOf("data=");
  const slice = raw.slice(dataStart);
  const rows: unknown[][] = [];
  const rowRe =
    /\[(\d+)\s*,\s*'((?:\\'|[^'])*)'\s*,\s*'((?:\\'|[^'])*)'(?:\s*,\s*'((?:\\'|[^'])*)')?/g;
  let match: RegExpExecArray | null;
  while ((match = rowRe.exec(slice))) {
    rows.push([
      Number(match[1]),
      unquotePyString(match[2]),
      unquotePyString(match[3]),
      match[4] ? unquotePyString(match[4]) : "",
    ]);
  }
  if (rows.length === 0) return undefined;
  return { columns: TIMETABLE_COLUMNS, data: rows };
}

/** Display dates as ``So 18.09.2011`` so Termine matches the season Spielplan. */
export function formatTimetableTable(
  table: TableData | undefined,
  language: "de" | "en" = "de",
): TableData | undefined {
  if (!table) return undefined;
  const fields = columnFields(table);
  const dateIdx = fields.indexOf("date");
  return {
    ...table,
    data: table.data.map((row) => {
      if (Array.isArray(row)) {
        if (dateIdx < 0) return row;
        const next = [...row];
        const key = parseSpielplanDateKey(next[dateIdx]);
        if (key) {
          const { weekday, displayDate } = formatSpielplanDate(key, language);
          next[dateIdx] = `${weekday} ${displayDate}`.trim();
        }
        return next;
      }
      const rec = { ...(row as Record<string, unknown>) };
      const key = parseSpielplanDateKey(rec.date);
      if (key) {
        const { weekday, displayDate } = formatSpielplanDate(key, language);
        rec.date = `${weekday} ${displayDate}`.trim();
      }
      return rec;
    }),
  };
}

export function parseTimetableEvents(
  table: unknown,
  league: SpielplanLeagueMeta,
): SpielplanEvent[] {
  const parsed = coerceTimetableTable(table);
  if (!parsed || !Array.isArray(parsed.data) || parsed.data.length === 0) {
    return [];
  }
  const fields = columnFields(parsed);
  const events: SpielplanEvent[] = [];
  for (const row of parsed.data) {
    if (row == null || (typeof row !== "object" && !Array.isArray(row))) continue;
    const typedRow = row as Record<string, unknown> | unknown[];
    const week = parseWeek(cellValue(typedRow, fields, "week"));
    if (week == null) continue;
    const venueRaw = asText(cellValue(typedRow, fields, "location"));
    events.push({
      league: league.value,
      leagueShort: league.short_name || league.value,
      leagueLong: league.long_name || league.short_name || league.value,
      week,
      dateKey: parseSpielplanDateKey(cellValue(typedRow, fields, "date")),
      venueRaw,
      venueKey: venueRaw ? normalizeVenueKey(venueRaw) : "",
    });
  }
  return events;
}

function pickDisplayName(events: SpielplanEvent[]): string {
  const counts = new Map<string, number>();
  for (const event of events) {
    const label = event.venueRaw.trim();
    if (!label) continue;
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  const ranked = [...counts.entries()].sort((a, b) => {
    if (b[1] !== a[1]) return b[1] - a[1];
    if (b[0].length !== a[0].length) return b[0].length - a[0].length;
    return a[0].localeCompare(b[0], "de");
  });
  return ranked[0]?.[0] ?? "";
}

function sortEvents(events: SpielplanEvent[]): SpielplanEvent[] {
  return [...events].sort((a, b) => {
    const byName = a.leagueShort.localeCompare(b.leagueShort, "de");
    if (byName !== 0) return byName;
    return a.week - b.week;
  });
}

function buildVenueGroups(events: SpielplanEvent[]): SpielplanVenueGroup[] {
  const byVenue = new Map<string, SpielplanEvent[]>();
  for (const event of events) {
    const list = byVenue.get(event.venueKey) ?? [];
    list.push(event);
    byVenue.set(event.venueKey, list);
  }
  return [...byVenue.entries()]
    .map(([venueKey, venueEvents]) => {
      const sorted = sortEvents(venueEvents);
      return {
        venueKey,
        displayName: pickDisplayName(sorted),
        shared: sorted.length > 1,
        events: sorted,
      };
    })
    .sort((a, b) => {
      if (a.shared !== b.shared) return a.shared ? -1 : 1;
      if (b.events.length !== a.events.length) return b.events.length - a.events.length;
      return a.displayName.localeCompare(b.displayName, "de");
    });
}

function toDay(
  dateKey: string | null,
  events: SpielplanEvent[],
  language: "de" | "en",
): SpielplanDay {
  const venues = buildVenueGroups(events);
  const formatted = dateKey
    ? formatSpielplanDate(dateKey, language)
    : { weekday: "", displayDate: "" };
  return {
    dateKey,
    weekday: formatted.weekday,
    displayDate: formatted.displayDate,
    leagueCount: events.length,
    venueCount: venues.length,
    venues,
  };
}

function collectSpielplanEvents(
  leagues: SpielplanLeagueMeta[],
  tables: unknown[],
): SpielplanEvent[] {
  const events: SpielplanEvent[] = [];
  leagues.forEach((league, index) => {
    events.push(...parseTimetableEvents(tables[index], league));
  });
  return events;
}

export function buildSeasonSpielplan(
  leagues: SpielplanLeagueMeta[],
  tables: unknown[],
  language: "de" | "en" = "de",
): SpielplanDay[] {
  const events = collectSpielplanEvents(leagues, tables);
  const byDate = new Map<string, SpielplanEvent[]>();
  const undated: SpielplanEvent[] = [];
  for (const event of events) {
    if (!event.dateKey) {
      undated.push(event);
      continue;
    }
    const list = byDate.get(event.dateKey) ?? [];
    list.push(event);
    byDate.set(event.dateKey, list);
  }

  const days = [...byDate.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([dateKey, dateEvents]) => toDay(dateKey, dateEvents, language));
  if (undated.length > 0) days.push(toDay(null, undated, language));
  return days;
}

const VENUE_FILLER = new Set([
  "am",
  "an",
  "auf",
  "bei",
  "das",
  "dem",
  "den",
  "der",
  "die",
  "im",
  "in",
  "und",
  "von",
]);

function venueTokens(name: string): string[] {
  const camel = name.replace(/([a-zäöüß])([A-ZÄÖÜ])/g, "$1 $2");
  return camel
    .split(/[\s\-/.,_]+/)
    .map((token) => token.replace(/[^\p{L}\p{N}]+/gu, ""))
    .filter((token) => token.length > 0 && !VENUE_FILLER.has(token.toLowerCase()));
}

function initialsOf(tokens: string[]): string {
  if (tokens.length === 0) return "";
  if (tokens.length === 1) return tokens[0].slice(0, 3).toUpperCase();
  return tokens
    .map((token) => token[0] ?? "")
    .join("")
    .toUpperCase()
    .slice(0, 4);
}

function venueAbbrevCandidates(displayName: string): string[] {
  const tokens = venueTokens(displayName);
  if (tokens.length === 0) return ["ORT"];
  const initials = initialsOf(tokens);
  const firstTwo = tokens
    .map((token) => token.slice(0, 2))
    .join("")
    .toUpperCase()
    .slice(0, 4);
  const firstPlusRest = (
    (tokens[0]?.slice(0, 2) ?? "") +
    tokens
      .slice(1)
      .map((token) => token[0] ?? "")
      .join("")
  )
    .toUpperCase()
    .slice(0, 4);
  return [...new Set([initials, firstPlusRest, firstTwo].filter((value) => value.length > 0))];
}

export function abbreviateVenues(
  venues: Array<{ venueKey: string; displayName: string }>,
): Map<string, string> {
  const used = new Set<string>();
  const abbrevs = new Map<string, string>();
  for (const venue of venues) {
    let chosen = "";
    for (const candidate of venueAbbrevCandidates(venue.displayName || venue.venueKey)) {
      if (!used.has(candidate)) {
        chosen = candidate;
        break;
      }
    }
    if (!chosen) {
      const base = venueAbbrevCandidates(venue.displayName || venue.venueKey)[0] ?? "ORT";
      let n = 2;
      chosen = `${base}${n}`;
      while (used.has(chosen)) {
        n += 1;
        chosen = `${base}${n}`;
      }
    }
    used.add(chosen);
    abbrevs.set(venue.venueKey, chosen);
  }
  return abbrevs;
}

export type SpielplanVenueLegend = {
  venueKey: string;
  displayName: string;
  abbrev: string;
  color: string;
};

export type SpielplanChartPoint = {
  league: string;
  leagueShort: string;
  leagueLong: string;
  week: number;
  dateKey: string;
  dateLabel: string;
  venueKey: string;
  venueName: string;
  abbrev: string;
  color: string;
};

export type SpielplanChartModel = {
  leagueLabels: string[];
  dateKeys: string[];
  dateLabels: string[];
  venues: SpielplanVenueLegend[];
  points: SpielplanChartPoint[];
  eventsByDate: Record<string, SpielplanEvent[]>;
  undated: SpielplanEvent[];
};

function sortLeagues(leagues: SpielplanLeagueMeta[]): SpielplanLeagueMeta[] {
  return [...leagues].sort((a, b) => {
    const levelDelta = getLeagueLevel(a.value) - getLeagueLevel(b.value);
    if (levelDelta !== 0) return levelDelta;
    return a.short_name.localeCompare(b.short_name, "de");
  });
}

export function buildSpielplanChartModel(
  leagues: SpielplanLeagueMeta[],
  tables: unknown[],
  language: "de" | "en" = "de",
  palette: readonly string[],
): SpielplanChartModel {
  const events = collectSpielplanEvents(leagues, tables);
  const dated = events.filter((event) => event.dateKey);
  const undated = events.filter((event) => !event.dateKey);
  const orderedLeagues = sortLeagues(leagues).filter((league) =>
    dated.some((event) => event.league === league.value),
  );
  const dateKeys = [...new Set(dated.map((event) => event.dateKey as string))].sort();
  const dateLabels = dateKeys.map((dateKey) => {
    const { weekday, displayDate } = formatSpielplanDate(dateKey, language);
    return `${weekday} ${displayDate.slice(0, 5)}`.trim();
  });

  const venueEvents = new Map<string, SpielplanEvent[]>();
  for (const event of dated) {
    const list = venueEvents.get(event.venueKey) ?? [];
    list.push(event);
    venueEvents.set(event.venueKey, list);
  }
  const venueRows = [...venueEvents.entries()]
    .map(([venueKey, list]) => ({
      venueKey,
      displayName: pickDisplayName(list) || venueKey,
    }))
    .sort((a, b) => a.displayName.localeCompare(b.displayName, "de"));
  const abbrevs = abbreviateVenues(venueRows);
  const venues: SpielplanVenueLegend[] = venueRows.map((row, index) => ({
    venueKey: row.venueKey,
    displayName: row.displayName,
    abbrev: abbrevs.get(row.venueKey) ?? row.displayName.slice(0, 3).toUpperCase(),
    color: palette[index % palette.length] ?? palette[0] ?? BRAND_PRIMARY,
  }));
  const venueByKey = new Map(venues.map((venue) => [venue.venueKey, venue]));

  const eventsByDate: Record<string, SpielplanEvent[]> = {};
  for (const event of dated) {
    const key = event.dateKey as string;
    const list = eventsByDate[key] ?? [];
    list.push(event);
    eventsByDate[key] = list;
  }
  for (const list of Object.values(eventsByDate)) {
    list.sort((a, b) => a.leagueShort.localeCompare(b.leagueShort, "de"));
  }

  const points: SpielplanChartPoint[] = dated.map((event) => {
    const venue = venueByKey.get(event.venueKey);
    const dateIndex = dateKeys.indexOf(event.dateKey as string);
    return {
      league: event.league,
      leagueShort: event.leagueShort,
      leagueLong: event.leagueLong,
      week: event.week,
      dateKey: event.dateKey as string,
      dateLabel: dateLabels[dateIndex] ?? event.dateKey ?? "",
      venueKey: event.venueKey,
      venueName: venue?.displayName ?? event.venueRaw,
      abbrev: venue?.abbrev ?? "ORT",
      color: venue?.color ?? palette[0] ?? BRAND_PRIMARY,
    };
  });

  return {
    leagueLabels: orderedLeagues.map((league) => league.short_name || league.value),
    dateKeys,
    dateLabels,
    venues,
    points,
    eventsByDate,
    undated,
  };
}
