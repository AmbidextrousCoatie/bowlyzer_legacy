import type { TableData } from "./types";

/** Resolve ``title_key`` on column groups/columns using the active UI language. */
export function localizeTableData(
  data: TableData,
  t: (key: string, fallback?: string) => string,
): TableData {
  return {
    ...data,
    columns: data.columns.map((group) => ({
      ...group,
      title: group.title_key ? t(group.title_key, group.title ?? "") : group.title,
      columns: group.columns?.map((col) => ({
        ...col,
        title: col.title_key ? t(col.title_key, col.title ?? "") : col.title,
      })),
    })),
  };
}
