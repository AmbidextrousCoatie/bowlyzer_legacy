/**
 * JSON shapes returned by the Flask league/team/tournament endpoints.
 * Backend column metadata uses a "groups of columns" structure even when there
 * are no group titles (in that case all titles are empty strings and the table
 * is rendered flat).
 */

export type ColumnDef = {
  field?: string;
  title?: string;
  align?: "left" | "center" | "right";
  width?: number | string;
  decimal_places?: number | string | null;
  sortable?: boolean;
  tooltip?: string;
  /** Per-column freeze; when any column in a group sets this, only those columns freeze (not the whole group). */
  frozen?: "left" | "right";
  cssClass?: string;
  headerClass?: string;
  style?: Record<string, string | number>;
};

export type ColumnGroup = {
  title?: string;
  columns?: ColumnDef[];
  frozen?: "left" | "right" | false | null;
  highlighted?: boolean;
  cssClass?: string;
};

export type CellMetaStyles = Record<string, string | number>;
/** Keyed as "rowIdx:colIdx". */
export type CellMetadata = Record<string, CellMetaStyles>;

export type RowMetaEntry = {
  styling?: Record<string, string | number>;
  /** Emitted by the Flask table payloads; aligns semantic separators with legacy/Jinja tables. */
  separator_before?: boolean;
  /** Server field for row role (e.g. summary / team / total). */
  rowType?: string;
  /** Optional client-side semantic alias when mapping row_metadata. */
  kind?: string;
} | null;

export type TableConfig = {
  compact?: boolean;
  stripedColGroups?: boolean;
};

export type SortDir = "asc" | "desc";

export type DefaultSort = { field: string; dir?: SortDir };

export type TableData = {
  columns: ColumnGroup[];
  data: Array<Record<string, unknown> | unknown[]>;
  cell_metadata?: CellMetadata;
  row_metadata?: RowMetaEntry[];
  config?: TableConfig;
  default_sort?: DefaultSort;
  title?: string;
  /** Free-form payload sent alongside the table (e.g. heatmap ranges). */
  metadata?: Record<string, unknown>;
};

export type DataTableOptions = {
  disablePositionCircle?: boolean;
  enableSpecialRowStyling?: boolean;
  tooltips?: boolean;
  teamField?: string | null;
  enableHeatMap?: boolean;
  /** When rendering multiple tables in a row, prevents the first table from
   *  resetting the global team color map. */
  disableTeamColorUpdate?: boolean;
};

export type FlatColumnInfo = {
  group: ColumnGroup;
  column: ColumnDef;
  groupIndex: number;
  columnIndex: number;
  field: string;
};
