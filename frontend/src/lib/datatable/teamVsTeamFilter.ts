import type { Tabulator } from "tabulator-tables";
import type { ColumnGroup, TableData } from "./types";

export type TeamVsTeamMetric = "points" | "score" | "both";

export type TeamVsTeamColumnFields = {
  pointsFields: string[];
  scoreFields: string[];
  otherFields: string[];
};

function flattenColumnFields(columns: ColumnGroup[]): string[] {
  const fields: string[] = [];
  for (const group of columns) {
    if (!Array.isArray(group.columns)) continue;
    for (const col of group.columns) {
      if (col.field) fields.push(col.field);
    }
  }
  return fields;
}

/** Classify matrix columns for points / pins toggling (matches legacy team-vs-team-utils). */
export function extractTeamVsTeamColumnFields(data: TableData): TeamVsTeamColumnFields {
  const pointsFields: string[] = [];
  const scoreFields: string[] = [];
  const otherFields: string[] = [];

  for (const field of flattenColumnFields(data.columns)) {
    const lower = field.toLowerCase();
    if (lower.includes("points")) {
      pointsFields.push(field);
    } else if (lower.includes("score")) {
      scoreFields.push(field);
    } else {
      otherFields.push(field);
    }
  }

  return { pointsFields, scoreFields, otherFields };
}

type TabulatorColumnLike = {
  getField: () => string | undefined;
  getColumns?: () => TabulatorColumnLike[];
  hide: () => void;
  show: () => void;
};

function collectLeafColumns(columns: TabulatorColumnLike[]): TabulatorColumnLike[] {
  const leaves: TabulatorColumnLike[] = [];
  for (const col of columns) {
    const children = col.getColumns?.();
    if (children && children.length > 0) {
      leaves.push(...collectLeafColumns(children));
    } else {
      const field = col.getField();
      if (field) leaves.push(col);
    }
  }
  return leaves;
}

/** Show/hide score and points columns without rebuilding the table. */
export function applyTeamVsTeamMetricFilter(
  tabulator: Tabulator,
  fields: TeamVsTeamColumnFields,
  metric: TeamVsTeamMetric,
): void {
  const { pointsFields, scoreFields, otherFields } = fields;

  let showFields: string[];
  let hideFields: string[];

  if (metric === "points") {
    showFields = [...pointsFields, ...otherFields];
    hideFields = scoreFields;
  } else if (metric === "score") {
    showFields = [...scoreFields, ...otherFields];
    hideFields = pointsFields;
  } else {
    showFields = [...pointsFields, ...scoreFields, ...otherFields];
    hideFields = [];
  }

  const showSet = new Set(showFields);
  const hideSet = new Set(hideFields);

  const rootColumns = tabulator.getColumns() as unknown as TabulatorColumnLike[];
  for (const col of collectLeafColumns(rootColumns)) {
    const field = col.getField();
    if (!field) continue;
    if (hideSet.has(field)) col.hide();
    else if (showSet.has(field)) col.show();
  }
}
