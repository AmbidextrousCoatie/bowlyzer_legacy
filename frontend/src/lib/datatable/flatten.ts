import type { CellMetaStyles, CellMetadata, ColumnGroup, FlatColumnInfo } from "./types";

export function flattenColumnMetadata(columnGroups: ColumnGroup[] = []): FlatColumnInfo[] {
  const flat: FlatColumnInfo[] = [];
  columnGroups.forEach((group, groupIndex) => {
    if (Array.isArray(group.columns)) {
      group.columns.forEach((column, columnIndex) => {
        const field = column.field ?? `col_${groupIndex}_${columnIndex}`;
        flat.push({ group, column, groupIndex, columnIndex, field });
      });
    }
  });
  return flat;
}

/** Backend keys cell metadata as "rowIdx:colIdx". Reindex by row → field for
 *  fast cell-level lookup inside the formatter. */
export function mapCellMetadata(
  cellMetadata: CellMetadata = {},
  columnOrder: FlatColumnInfo[] = [],
): Record<number, Record<string, CellMetaStyles>> {
  const mapped: Record<number, Record<string, CellMetaStyles>> = {};
  Object.entries(cellMetadata).forEach(([key, styles]) => {
    const [rowStr, colStr] = key.split(":");
    const rowIndex = parseInt(rowStr, 10);
    const colIndex = parseInt(colStr, 10);
    const columnInfo = columnOrder[colIndex];
    if (!columnInfo || Number.isNaN(rowIndex)) return;
    const field = columnInfo.field;
    if (!mapped[rowIndex]) mapped[rowIndex] = {};
    mapped[rowIndex][field] = styles;
  });
  return mapped;
}

export function applyElementStyles(
  element: HTMLElement | null | undefined,
  styles: Record<string, string | number> = {},
): void {
  if (!element || !styles) return;
  Object.entries(styles).forEach(([prop, value]) => {
    if (value !== undefined && value !== null) {
      // CSSStyleDeclaration is index-signature-friendly via setProperty for
      // kebab-case, but the legacy code wrote camelCase via element.style[prop].
      // Mirror that behavior here.
      (element.style as unknown as Record<string, string | number>)[prop] = value;
    }
  });
}

export function parseColumnWidth(width: number | string | undefined): number | undefined {
  if (width === undefined || width === null || width === "") return undefined;
  if (typeof width === "number") return width;
  const parsed = parseInt(width, 10);
  return Number.isNaN(parsed) ? undefined : parsed;
}
