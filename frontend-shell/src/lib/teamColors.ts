/**
 * Must match `TEAM_COLOR_PALETTES` in `app/static/js/theme/color-utils.js` (legacy UI).
 */
import { TEAM_PALETTES } from "./theme";

export const TEAM_COLOR_PALETTES = TEAM_PALETTES;

export type TeamPaletteName = keyof typeof TEAM_COLOR_PALETTES;

function parseNumericCell(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = parseFloat(v.replace(",", ".").trim());
    if (!Number.isNaN(n) && Number.isFinite(n)) return n;
  }
  return null;
}

/** Match API row key case-insensitively (e.g. `pos`, `team`). */
function findRowKey(row: Record<string, unknown>, candidates: string[]): string | null {
  const keys = Object.keys(row);
  const lowerToActual = new Map(keys.map((k) => [k.toLowerCase(), k]));
  for (const c of candidates) {
    const actual = lowerToActual.get(c.toLowerCase());
    if (actual !== undefined) return actual;
  }
  return null;
}

/** Standings sort: rank column ascending (1 = top), else points desc, then pins/score desc — matches typical league tables. */
const RANK_FIELD_CANDIDATES = ["pos", "position", "rank", "place", "standing", "team_position", "platz"];
const POINTS_FIELD_CANDIDATES = ["season_points", "points", "pts", "total_points", "week_points", "matchday_points"];
const SCORE_TIEBREAK_CANDIDATES = ["season_score", "pins", "score", "total_pins"];

const TEAM_FIELD_CANDIDATES = ["team_name", "team", "club", "name"];

/**
 * Team names in **league order** (1st place → first palette color, 2nd → second, …).
 * Sorts rows before extracting names so colors track the table from top to bottom.
 */
export function orderedTeamNamesForPalette(rows: Array<Record<string, unknown>>): string[] {
  if (rows.length === 0) return [];
  const sample = rows[0];
  const teamKey =
    findRowKey(sample, [...TEAM_FIELD_CANDIDATES]) ??
    Object.keys(sample).find((k) => typeof sample[k] === "string");
  if (!teamKey) return [];

  const rankKey = findRowKey(sample, RANK_FIELD_CANDIDATES);
  const pointsKey = findRowKey(sample, POINTS_FIELD_CANDIDATES);
  const scoreKey = findRowKey(sample, SCORE_TIEBREAK_CANDIDATES);

  const teamTie = (a: Record<string, unknown>, b: Record<string, unknown>) => {
    const sa = String(a[teamKey] ?? "")
      .trim()
      .toLowerCase();
    const sb = String(b[teamKey] ?? "")
      .trim()
      .toLowerCase();
    return sa.localeCompare(sb);
  };

  const sorted = [...rows].sort((a, b) => {
    if (rankKey) {
      const ra = parseNumericCell(a[rankKey]);
      const rb = parseNumericCell(b[rankKey]);
      if (ra !== null && rb !== null && ra !== rb) return ra - rb;
    }
    if (pointsKey) {
      const pa = parseNumericCell(a[pointsKey]);
      const pb = parseNumericCell(b[pointsKey]);
      if (pa !== null && pb !== null && pa !== pb) return pb - pa;
    }
    if (scoreKey) {
      const sa = parseNumericCell(a[scoreKey]);
      const sb = parseNumericCell(b[scoreKey]);
      if (sa !== null && sb !== null && sa !== sb) return sb - sa;
    }
    return teamTie(a, b);
  });

  return sorted
    .map((row) => row[teamKey])
    .filter((v): v is string => typeof v === "string" && v.trim().length > 0);
}

/**
 * Same team order as v1 `season/team-points` chart series — backend `sorted_by_total`, matching legacy `createLineChart` + `updateTeamColorMap(order)`.
 */
export function orderedTeamNamesFromPointsChartSeries(series: Array<{ name: string }>): string[] {
  return series
    .map((s) => s.name)
    .filter((n) => typeof n === "string" && n.trim().length > 0);
}

export function buildTeamColorMap(orderedTeams: string[], paletteName: TeamPaletteName): Record<string, string> {
  const palette = TEAM_COLOR_PALETTES[paletteName];
  const map: Record<string, string> = {};
  orderedTeams.forEach((team, idx) => {
    const key = team.trim();
    if (!key) return;
    map[key] = palette[idx % palette.length];
  });
  return map;
}

/** Lookup team color; keys may differ by whitespace/casing vs standings. */
export function lookupTeamColor(teamColors: Record<string, string>, teamName: string): string | undefined {
  const t = teamName.trim();
  if (!t) return undefined;
  if (teamColors[t]) return teamColors[t];
  const lower = t.toLowerCase();
  for (const k of Object.keys(teamColors)) {
    if (k.trim().toLowerCase() === lower) return teamColors[k];
  }
  return undefined;
}

export function getTeamColor(teamColors: Record<string, string>, teamName: unknown): string | undefined {
  if (typeof teamName !== "string") return undefined;
  return lookupTeamColor(teamColors, teamName);
}

const TEAM_NAME_FIELDS = ["team_name", "team", "club", "name", "player_name", "opponent_name"] as const;

/**
 * Color for team-themed UI on a table row. Prefer team-identifying columns;
 * do not use position/rank cells as the team key (avoids grey dots on pos columns).
 */
export function resolveTeamColorForRow(
  row: Record<string, unknown>,
  teamColors: Record<string, string> | undefined,
): string | undefined {
  if (!teamColors || Object.keys(teamColors).length === 0) return undefined;

  for (const field of TEAM_NAME_FIELDS) {
    const v = row[field];
    if (typeof v !== "string") continue;
    const c = lookupTeamColor(teamColors, v);
    if (c) return c;
  }

  return undefined;
}
