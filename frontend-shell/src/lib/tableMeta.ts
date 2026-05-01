import type { TableColumnGroup, TableData } from "../types";

export type FlatColumnOrder = Array<{ groupIndex: number; columnIndex: number; field: string }>;

/**
 * Stable signature for column layout (groups, fields, flags). Row data is ignored.
 * Used to decide whether Tabulator needs `setColumns` vs `replaceData` only.
 */
export function tableSchemaSignature(table: TableData): string {
  return JSON.stringify(
    table.columns.map((g) => ({
      t: g.title,
      fz: g.frozen,
      hi: g.highlighted,
      cc: g.cssClass,
      cols: g.columns.map((c) => ({
        f: c.field,
        a: c.align,
        s: c.sortable,
        w: c.width,
        d: c.decimal_places,
        tip: c.tooltip,
        css: c.cssClass,
        hc: c.headerClass,
      })),
    })),
  );
}

export function flattenColumnOrder(groups: TableColumnGroup[]): FlatColumnOrder {
  const flat: FlatColumnOrder = [];
  groups.forEach((group, groupIndex) => {
    group.columns.forEach((_col, columnIndex) => {
      flat.push({
        groupIndex,
        columnIndex,
        field: _col.field,
      });
    });
  });
  return flat;
}

/**
 * Legacy Tabulator indexes cell_metadata by flattened column index `"rowIndex:colIndex"`.
 */
export function mapCellMetadataByField(
  cellMetadata: Record<string, Record<string, unknown>> | undefined,
  fieldOrder: string[],
): Map<string, Record<string, unknown>> {
  const byFieldKey = new Map<string, Record<string, unknown>>();
  if (!cellMetadata) return byFieldKey;
  Object.entries(cellMetadata).forEach(([key, styles]) => {
    const parts = key.split(":");
    if (parts.length !== 2) return;
    const rowIndex = parseInt(parts[0], 10);
    const colIndex = parseInt(parts[1], 10);
    if (Number.isNaN(rowIndex) || Number.isNaN(colIndex)) return;
    const field = fieldOrder[colIndex];
    if (!field) return;
    byFieldKey.set(`${rowIndex}:${field}`, styles);
  });
  return byFieldKey;
}

export function camelToCssProperty(prop: string): string {
  return prop.replace(/([A-Z])/g, "-$1").toLowerCase();
}

export function applyLegacyStyle(el: HTMLElement, styles: Record<string, unknown>) {
  Object.entries(styles).forEach(([property, value]) => {
    if (value === undefined || value === null) return;
    if (property === "backgroundColor") {
      el.style.setProperty("background-color", String(value), "important");
      return;
    }
    el.style.setProperty(camelToCssProperty(property), String(value));
  });
}

/** Column `style` from JSON applies to cells (legacy Tabulator formatter). */
export function mergeColumnStyleOnto(el: HTMLElement, styles: Record<string, string> | undefined) {
  if (!styles) return;
  Object.entries(styles).forEach(([property, value]) => {
    if (!value) return;
    el.style.setProperty(camelToCssProperty(property), value);
  });
}

export function normalizeDefaultSort(cfg: Record<string, unknown> | undefined): { field: string; dir: "asc" | "desc" } | undefined {
  if (!cfg) return undefined;
  const ds =
    (cfg.defaultSort as { field?: string; dir?: string } | undefined) ||
    (cfg.default_sort as { field?: string; dir?: string } | undefined);
  if (!ds?.field || typeof ds.field !== "string") return undefined;
  const dirRaw = ds.dir ?? "desc";
  const dir = String(dirRaw).toLowerCase() === "asc" ? "asc" : "desc";
  return { field: ds.field, dir };
}

export function decimalsOrString(val: unknown, dp: number | undefined): string {
  if (val === null || val === undefined) return "";
  if (typeof val === "number" && dp !== undefined && !Number.isNaN(dp)) {
    return val.toFixed(dp);
  }
  if (typeof val === "number") return String(val);
  return String(val);
}
