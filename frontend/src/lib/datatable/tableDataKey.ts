import type { TableData } from "./types";

/** Stable identity for table payload — avoids Tabulator teardown when React Query reuses content. */
export function getTableDataKey(data: TableData): string {
  try {
    return JSON.stringify({
      columns: data.columns,
      data: data.data,
      cell_metadata: data.cell_metadata,
      row_metadata: data.row_metadata,
      config: data.config,
      default_sort: data.default_sort,
      metadata: data.metadata,
    });
  } catch {
    return "";
  }
}
