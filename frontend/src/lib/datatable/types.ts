/**
 * JSON shapes returned by the Flask league/team/tournament endpoints.
 * Backend column metadata uses a "groups of columns" structure even when there
 * are no group titles (in that case all titles are empty strings and the table
 * is rendered flat).
 */

export type ColumnDef = {
  field?: string;
  title?: string;
  /** When set, React replaces ``title`` via ``/league/get_translations``. */
  title_key?: string;
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
  title_key?: string;
  columns?: ColumnDef[];
  frozen?: "left" | "right" | false | null;
  highlighted?: boolean;
  /** Stripe/highlight column headers only; body cells stay plain. */
  highlight_header_only?: boolean;
  cssClass?: string;
};

export type CellMetaStyles = Record<string, string | number>;
/** Keyed as "rowIdx:colIdx". */
export type CellMetadata = Record<string, CellMetaStyles>;

export type RowMetaEntry = {
  styling?: Record<string, string | number>;
  /** Row wash + left bar (Einzeldurchschnitte-style); independent of enableSpecialRowStyling. */
  rowAccentColor?: string;
  /** Emitted by the Flask table payloads; aligns semantic separators with legacy/Jinja tables. */
  separator_before?: boolean;
  /** Server field for row role (e.g. summary / team / total). */
  rowType?: string;
  /** Optional client-side semantic alias when mapping row_metadata. */
  kind?: string;
  /** Row is clickable; navigates via parent `onReady` handler (e.g. player Saisonstatistik). */
  eventNav?: boolean;
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
  description?: string;
  /** Free-form payload sent alongside the table (e.g. heatmap ranges). */
  metadata?: Record<string, unknown>;
};

export type LeagueTableNavigation = {
  season: string;
  league: string;
  /** Latest week for ranking-column / default week links. */
  defaultWeek: number | string;
  onNavigate: (path: string) => void;
};

export type DataTableOptions = {
  disablePositionCircle?: boolean;
  enableSpecialRowStyling?: boolean;
  tooltips?: boolean;
  teamField?: string | null;
  /** League id/code so colors are scoped when the same team name appears in multiple leagues. */
  teamColorLeague?: string | null;
  enableHeatMap?: boolean;
  /** When rendering multiple tables in a row, prevents the first table from
   *  resetting the global team color map. */
  disableTeamColorUpdate?: boolean;
  /** Standings-style tables: assign palette by row order (legacy chart alignment). */
  seedTeamColorsFromTable?: boolean;
  /** Zebra row backgrounds. Default on; disable for short tables (e.g. standings). */
  stripedRows?: boolean;
  /** Alternating column-group shading. When omitted, follows payload `config.stripedColGroups`. */
  stripedColumnGroups?: boolean;
  /** Stripe palette style; `league` uses subtle rainbowPastel[0] tints. */
  columnGroupStripeVariant?: "default" | "league";
  /** Column-group drill-down for league standings tables (season / week / team views). */
  leagueNavigation?: LeagueTableNavigation;
  /** Team-vs-team matrix: rebuild with only Punkte / Pins / Beides columns. */
  teamVsTeamMetric?: "points" | "score" | "both";
  /** Tournament leaderboard: row accent from cut cell metadata (green / yellow), not team colors. */
  tournamentCutRowStyling?: boolean;
  /** Freeze the first N column groups on the left (Tabulator group-level freeze). */
  freezeColumnGroupCount?: number;
  /** Body cells in these column group indexes use semibold weight. */
  boldColumnGroupIndexes?: number[];
  /** When false, column resize handles are disabled (default: true). */
  resizableColumns?: boolean;
  /** Team performance tables: seed player/team colors by performance rank order. */
  playerColorOrder?: string[];
  performanceTeamName?: string;
};

export type FlatColumnInfo = {
  group: ColumnGroup;
  column: ColumnDef;
  groupIndex: number;
  columnIndex: number;
  field: string;
};
