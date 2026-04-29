export type OptionItem = { value: string; label: string };

export type ApiResponse<T> = { success: true; data: T } | { success: false; error: { code: string; message: string } };

export type ListData = { items: OptionItem[] };

export type TableData = {
  title?: string;
  columns: Array<{ title: string; columns: Array<{ title: string; field: string }> }>;
  rows: Array<Record<string, unknown>>;
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
