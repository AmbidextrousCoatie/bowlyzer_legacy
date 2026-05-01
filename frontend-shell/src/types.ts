export type OptionItem = { value: string; label: string };

export type ApiResponse<T> = { success: true; data: T } | { success: false; error: { code: string; message: string } };

export type ListData = { items: OptionItem[] };

export type TableColumn = {
  title: string;
  field: string;
  align?: "left" | "center" | "right";
  /** Default true in backend; omit means sortable */
  sortable?: boolean;
  width?: string;
  tooltip?: string;
  decimal_places?: number;
  style?: Record<string, string>;
  cssClass?: string;
  headerClass?: string;
};

export type TableColumnGroup = {
  title: string;
  columns: TableColumn[];
  frozen?: "left" | "right";
  highlighted?: boolean;
  /** Extra header cell class(es) merged in legacy renderer */
  cssClass?: string;
};

export type TableData = {
  title?: string;
  description?: string;
  columns: TableColumnGroup[];
  rows: Array<Record<string, unknown>>;
  /**
   * Table-wide flags from backend `TableData.config`:
   * compact, stripedColGroups, stripRows, stickyHeader (when present).
   */
  config?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  /** Row-level styling payloads (indexed by visible row position) */
  row_metadata?: Array<Record<string, unknown>>;
  /** Cell overrides keyed `"rowIdx:flatColIdx"` — see `cell_metadata` in legacy Flask tables */
  cell_metadata?: Record<string, Record<string, unknown>>;
};

export type ChartData = {
  title?: string;
  xAxis: { categories: Array<string | number> };
  series: Array<{ id: string; name: string; data: Array<number | null> }>;
};

export type ColorMode = "off" | "sequential" | "diverging";
export type HeatmapNormMode = "global" | "row";
export type HeatmapGroupingMode = "auto" | "single";
export type TeamWeekView = "classic" | "individual" | "head-to-head";

export type HonorItem = { label: string; value: string };
export type HonorCardView = { title: string; items: HonorItem[]; raw?: unknown };
