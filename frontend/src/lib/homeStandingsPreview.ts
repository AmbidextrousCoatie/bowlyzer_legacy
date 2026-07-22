import type { TableData } from "./datatable/types";
import { flattenColumnMetadata } from "./datatable/flatten";

export type StandingsPreviewRow = {
  cells: string[];
};

export type StandingsPreview = {
  league: string;
  leagueLong?: string;
  week: number | string;
  headers: string[];
  rows: StandingsPreviewRow[];
};

const PREVIEW_ROW_LIMIT = 5;
const PREVIEW_COLUMN_LIMIT = 4;

const TEAM_FIELD_CANDIDATES = ["team", "team_name", "Team", "Mannschaft"];
const RANK_FIELD_CANDIDATES = ["rank", "position", "platz", "Pos", "Rang"];
const SCORE_FIELD_CANDIDATES = [
  "points",
  "punkte",
  "total",
  "gesamt",
  "score",
  "avg",
  "average",
  "schnitt",
];

function rowValue(row: Record<string, unknown>, field: string): unknown {
  return row[field];
}

function formatCell(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "number" && Number.isFinite(value)) {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return String(value);
}

function pickField(fields: string[], candidates: string[]): string | null {
  const normalized = new Map(fields.map((f) => [f.toLowerCase(), f]));
  for (const candidate of candidates) {
    const hit = normalized.get(candidate.toLowerCase());
    if (hit) return hit;
  }
  return null;
}

function isSummaryRow(row: Record<string, unknown>, rowIndex: number, rowMetadata?: TableData["row_metadata"]) {
  const meta = rowMetadata?.[rowIndex];
  if (meta?.rowType && meta.rowType !== "team" && meta.rowType !== "data") return true;
  if (meta?.kind && meta.kind !== "team" && meta.kind !== "data") return true;
  const teamVal = TEAM_FIELD_CANDIDATES.map((f) => row[f]).find((v) => v != null && v !== "");
  return !teamVal;
}

/**
 * Build a compact standings snippet for the landing page (table-first, Excel-like).
 */
export function buildStandingsPreview(
  standings: TableData,
  meta: { league: string; leagueLong?: string; week: number | string },
): StandingsPreview | null {
  const flat = flattenColumnMetadata(standings.columns);
  const fields = flat.map((c) => c.field);

  const rankField = pickField(fields, RANK_FIELD_CANDIDATES);
  const teamField = pickField(fields, TEAM_FIELD_CANDIDATES);
  const scoreField = pickField(fields, SCORE_FIELD_CANDIDATES);

  const selectedFields = [rankField, teamField, scoreField].filter(Boolean) as string[];
  if (!teamField) {
    const fallback = fields.slice(0, PREVIEW_COLUMN_LIMIT);
    if (fallback.length === 0) return null;
    return buildFromFields(standings, meta, fallback, flat);
  }

  const ordered = selectedFields.length > 0 ? selectedFields : [teamField];
  const headers = ordered.map((field) => {
    const col = flat.find((c) => c.field === field);
    return col?.column.title || field;
  });

  const rows: StandingsPreviewRow[] = [];
  for (let i = 0; i < standings.data.length && rows.length < PREVIEW_ROW_LIMIT; i++) {
    const raw = standings.data[i];
    if (!raw || Array.isArray(raw)) continue;
    const row = raw as Record<string, unknown>;
    if (isSummaryRow(row, i, standings.row_metadata)) continue;
    rows.push({
      cells: ordered.map((field) => formatCell(rowValue(row, field))),
    });
  }

  if (rows.length === 0) return null;

  return {
    league: meta.league,
    leagueLong: meta.leagueLong,
    week: meta.week,
    headers,
    rows,
  };
}

function buildFromFields(
  standings: TableData,
  meta: { league: string; leagueLong?: string; week: number | string },
  fields: string[],
  flat: ReturnType<typeof flattenColumnMetadata>,
): StandingsPreview {
  const headers = fields.map((field) => {
    const col = flat.find((c) => c.field === field);
    return col?.column.title || field;
  });

  const rows: StandingsPreviewRow[] = [];
  for (let i = 0; i < standings.data.length && rows.length < PREVIEW_ROW_LIMIT; i++) {
    const raw = standings.data[i];
    if (!raw || Array.isArray(raw)) continue;
    const row = raw as Record<string, unknown>;
    if (isSummaryRow(row, i, standings.row_metadata)) continue;
    rows.push({
      cells: fields.map((field) => formatCell(rowValue(row, field))),
    });
  }

  return {
    league: meta.league,
    leagueLong: meta.leagueLong,
    week: meta.week,
    headers,
    rows,
  };
}

export function preferLeagueEntry<T extends { league: string }>(
  leagues: T[],
  preferredShortName = "BayL",
): T | null {
  if (leagues.length === 0) return null;
  const hit = leagues.find(
    (l) => l.league.trim().toLowerCase() === preferredShortName.toLowerCase(),
  );
  return hit ?? leagues[0];
}
