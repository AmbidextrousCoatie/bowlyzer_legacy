import {
  TabulatorFull as Tabulator,
  type CellComponent,
  type ColumnDefinition,
  type Options,
  type RowComponent,
} from "tabulator-tables";

import {
  assignGroupStripeCss,
  DEFAULT_STRIPE_PALETTE,
  getHeatMapColor,
  getPlayerColorMap,
  getTeamColor,
  getTeamColorMap,
  injectStripeCss,
  TOURNAMENT_CUT_ROW_COLORS,
  seedPlayerColorsFromPerformanceOrder,
  toRgba,
  ensureTeamColors,
  extractTeamNamesFromTablePayload,
  isTeamVsTeamComparisonTable,
  seedTeamColorsFromTablePayload,
  updateTeamColorMap,
} from "../color-utils";
import {
  groupIndexFromCellElement,
  resolveLeagueCellNavPath,
  type LeagueNavContext,
} from "../leagueNavigation";
import {
  applyElementStyles,
  flattenColumnMetadata,
  mapCellMetadata,
  parseColumnWidth,
} from "./flatten";
import { filterTableColumnsForMetric } from "./teamVsTeamFilter";
import type {
  CellMetaStyles,
  ColumnDef,
  DataTableOptions,
  FlatColumnInfo,
  TableData,
} from "./types";

const HIGHLIGHT_STYLES = {
  headerBackgroundColor: "rgba(0, 0, 0, 0.05)",
  cellBackgroundColor: "rgba(0, 0, 0, 0.03)",
  headerFontWeight: "900",
  cellFontWeight: "700",
};

export type DataTableHandle = {
  tabulator: Tabulator;
  destroy: () => void;
};

type RowObject = Record<string, unknown> & {
  __rowIndex: number;
  __rowMeta?: {
    styling?: Record<string, string | number>;
    rowAccentColor?: string;
    separator_before?: boolean;
    kind?: string;
  } | null;
};

function hasSemanticSeparator(rowMeta: RowObject["__rowMeta"]): boolean {
  if (!rowMeta) return false;
  if (rowMeta.separator_before === true) return true;
  const rowTypeRaw =
    typeof rowMeta.kind === "string"
      ? rowMeta.kind
      : typeof (rowMeta as Record<string, unknown>).rowType === "string"
        ? ((rowMeta as Record<string, unknown>).rowType as string)
        : "";
  const rowType = rowTypeRaw.toLowerCase();
  return rowType === "summary" || rowType === "team" || rowType === "total";
}

/**
 * Build a Tabulator instance against the given container using the backend
 * table-data shape. Returns the instance + a destroy callback for React
 * lifecycle integration.
 */
export function createDataTable(
  container: HTMLElement,
  rawData: TableData,
  rawOptions: DataTableOptions = {},
): DataTableHandle | null {
  if (!rawData || !rawData.columns || !rawData.data) {
    console.error("[DataTable] Invalid data format");
    return null;
  }

  const settings: Required<
    Omit<
      DataTableOptions,
      | "stripedColumnGroups"
      | "columnGroupStripeVariant"
      | "leagueNavigation"
      | "teamVsTeamMetric"
      | "tournamentCutRowStyling"
      | "playerColorOrder"
      | "performanceTeamName"
    >
  > = {
    disablePositionCircle: false,
    enableSpecialRowStyling: false,
    tooltips: true,
    teamField: null,
    teamColorLeague: null,
    enableHeatMap: false,
    disableTeamColorUpdate: false,
    seedTeamColorsFromTable: false,
    stripedRows: true,
    ...rawOptions,
  };

  const tournamentCutRowStyling = rawOptions.tournamentCutRowStyling === true;

  // Defensive copy so we don't mutate caller's data when we apply decimal
  // formatting / cssClass injection below.
  const data: TableData = {
    ...rawData,
    columns: rawData.columns.map((g) => ({
      ...g,
      columns: Array.isArray(g.columns) ? g.columns.map((c) => ({ ...c })) : g.columns,
    })),
    data: Array.isArray(rawData.data)
      ? rawData.data.map((row) =>
          Array.isArray(row) ? [...row] : { ...(row as Record<string, unknown>) },
        )
      : rawData.data,
  };

  const tableConfig = data.config ?? {};
  const isCompactLayout = tableConfig.compact === true;
  const useStripedColumnGroups =
    rawOptions.stripedColumnGroups !== undefined
      ? rawOptions.stripedColumnGroups
      : tableConfig.stripedColGroups === true;

  const columnGroupStripeVariant: "default" | "league" =
    rawOptions.columnGroupStripeVariant ??
    (useStripedColumnGroups &&
    (tableConfig.stripedColGroups === true || rawOptions.stripedColumnGroups === true)
      ? "league"
      : "default");

  if (container.style.width === "") {
    container.style.width = "100%";
  }

  if (rawOptions.playerColorOrder?.length && rawOptions.performanceTeamName) {
    const teamLabel = rawOptions.performanceTeamName;
    seedPlayerColorsFromPerformanceOrder(rawOptions.playerColorOrder, teamLabel, [
      teamLabel,
      `${teamLabel} (Team)`,
      `${teamLabel} (Team Average)`,
    ]);
  }

  const teamVsTeamMetric = rawOptions.teamVsTeamMetric;
  const columnsForBuild =
    teamVsTeamMetric !== undefined
      ? filterTableColumnsForMetric(data.columns, teamVsTeamMetric)
      : data.columns;

  const fullColumnOrder = flattenColumnMetadata(data.columns);
  const columnOrder = flattenColumnMetadata(columnsForBuild);
  if (!columnOrder.length) {
    console.warn("[DataTable] No column definitions");
    container.innerHTML = `<div class="ds-table-empty">${
      data.title?.includes("Fehler") ? data.title : "No column definitions"
    }</div>`;
    return null;
  }

  const rankFieldForCut = tournamentCutRowStyling
    ? (columnOrder.find((c) => c.field === "rank" || c.field === "pos" || c.field === "overall_rank")
        ?.field ?? columnOrder[0]?.field ?? "rank")
    : null;

  const columnLookup: Record<string, FlatColumnInfo> = {};
  columnOrder.forEach((info) => {
    columnLookup[`${info.groupIndex}-${info.columnIndex}`] = info;
  });

  /** Backend rows are arrays in full column order; map field → index for safe lookups when columns are filtered. */
  const arrayIndexByField = new Map<string, number>();
  fullColumnOrder.forEach((info, idx) => {
    arrayIndexByField.set(info.field, idx);
  });

  const teamFieldGuess = data.columns?.[0]?.columns?.[1]?.field ?? null;
  const teamField = settings.teamField ?? teamFieldGuess;

  // Pre-compute decimal-place formatting per field
  const decimalPlacesMap: Record<string, number> = {};
  data.columns.forEach((group) => {
    if (!Array.isArray(group.columns)) return;
    group.columns.forEach((column) => {
      if (column.decimal_places !== undefined && column.decimal_places !== null && column.field) {
        decimalPlacesMap[column.field] = parseInt(String(column.decimal_places), 10);
      }
    });
  });

  // Apply decimal formatting up front so sort/data agrees with what's rendered
  if (Object.keys(decimalPlacesMap).length > 0 && Array.isArray(data.data)) {
    data.data = data.data.map((row) => {
      if (Array.isArray(row)) {
        return row.map((cell, idx) => {
          const info = fullColumnOrder[idx];
          if (info && decimalPlacesMap[info.field] !== undefined) {
            return formatDecimal(cell, decimalPlacesMap[info.field]);
          }
          return cell;
        });
      }
      if (typeof row === "object" && row !== null) {
        const formatted = { ...(row as Record<string, unknown>) };
        Object.keys(decimalPlacesMap).forEach((field) => {
          if (formatted[field] !== undefined && formatted[field] !== null) {
            formatted[field] = formatDecimal(formatted[field], decimalPlacesMap[field]);
          }
        });
        return formatted;
      }
      return row;
    });
  }

  const cellMetadataMap = mapCellMetadata(data.cell_metadata ?? {}, fullColumnOrder);
  const rowMetadataMap: Record<number, NonNullable<TableData["row_metadata"]>[number]> = {};
  (data.row_metadata ?? []).forEach((meta, idx) => {
    rowMetadataMap[idx] = meta ?? {};
  });

  const isArrayFormat =
    Array.isArray(data.data) && data.data.length > 0 && Array.isArray(data.data[0]);

  // Heatmap: bucket fields by data type, compute global min/max per bucket.
  const heatmapRanges: Record<string, { min: number; max: number }> = {};
  if (settings.enableHeatMap && data.data && data.data.length > 0) {
    const meta = data.metadata ?? {};
    const scoreRange = meta.score_range as { min: number; max: number } | undefined;
    const pointsRange = meta.points_range as { min: number; max: number } | undefined;
    if (
      isTeamVsTeamComparisonTable(data) &&
      scoreRange &&
      pointsRange &&
      Number.isFinite(scoreRange.min) &&
      Number.isFinite(scoreRange.max) &&
      Number.isFinite(pointsRange.min) &&
      Number.isFinite(pointsRange.max)
    ) {
      columnOrder.forEach((info) => {
        const lower = info.field.toLowerCase();
        if (lower.includes("points")) {
          heatmapRanges[info.field] = { min: pointsRange.min, max: pointsRange.max };
        } else if (lower.includes("score")) {
          heatmapRanges[info.field] = { min: scoreRange.min, max: scoreRange.max };
        }
      });
    } else {
    const typeFields: Record<"score" | "points", string[]> = { score: [], points: [] };
    columnOrder.forEach((info) => {
      const lower = info.field.toLowerCase();
      if (lower.includes("points")) {
        typeFields.points.push(info.field);
      } else if (
        lower.includes("score") ||
        lower.includes("pins") ||
        lower.includes("avg") ||
        lower.includes("average")
      ) {
        typeFields.score.push(info.field);
      }
    });
    (Object.keys(typeFields) as Array<keyof typeof typeFields>).forEach((type) => {
      const fields = typeFields[type];
      if (fields.length === 0) return;
      const values: number[] = [];
      fields.forEach((field) => {
        data.data.forEach((row) => {
          let v: unknown = null;
          if (isArrayFormat) {
            const colIdx = arrayIndexByField.get(field);
            if (colIdx !== undefined && Array.isArray(row) && colIdx < row.length) {
              v = row[colIdx];
            }
          } else if (typeof row === "object" && row !== null) {
            v = (row as Record<string, unknown>)[field];
          }
          const num = toFiniteNumber(v);
          if (num !== null) values.push(num);
        });
      });
      if (values.length > 0) {
        const min = Math.min(...values);
        const max = Math.max(...values);
        if (min !== max && Number.isFinite(min) && Number.isFinite(max)) {
          fields.forEach((field) => {
            heatmapRanges[field] = { min, max };
          });
        }
      }
    });
    }
  }

  // Transform rows into objects keyed by field, with __rowIndex / __rowMeta
  // attached for formatter access.
  const transformedData: RowObject[] = data.data.map((row, rowIndex) => {
    const obj: RowObject = { __rowIndex: rowIndex };
    if (isArrayFormat) {
      columnOrder.forEach((info) => {
        const colIdx = arrayIndexByField.get(info.field);
        if (colIdx !== undefined) {
          obj[info.field] = (row as unknown[])[colIdx];
        }
      });
    } else {
      const r = row as Record<string, unknown>;
      columnOrder.forEach((info) => {
        obj[info.field] = r[info.field];
      });
    }
    if (rowMetadataMap[rowIndex]) {
      obj.__rowMeta = rowMetadataMap[rowIndex];
    }
    return obj;
  });

  // Detect group structure: if every group title is empty, render flat.
  const hasGroupTitles = columnsForBuild.some((g) => g.title && g.title.trim() !== "");

  if (useStripedColumnGroups && hasGroupTitles) {
    assignGroupStripeCss(columnsForBuild);
    injectStripeCss(columnsForBuild.length, {
      variant: columnGroupStripeVariant,
      palette: DEFAULT_STRIPE_PALETTE,
      headerAlpha: isCompactLayout ? 0.3 : 0.2,
      cellAlpha: 0.1,
    });
  }

  // ----- Formatter (shared across flat / grouped branches) -----
  const makeFormatter =
    (
      column: ColumnDef,
      info: FlatColumnInfo,
      isHighlighted: boolean,
      contextGroupIndex: number,
      contextColumnIndex: number,
    ) =>
    (cell: CellComponent): string => {
      const value = cell.getValue();
      const element = cell.getElement();
      const row = cell.getRow();
      if (!row) return "";
      const rowData = row.getData() as RowObject;
      const rowIdx = rowData.__rowIndex;
      const field = info.field;

      if (useStripedColumnGroups && hasGroupTitles) {
        element.classList.add("col-group-" + info.groupIndex);
      }

      if (isHighlighted) {
        element.classList.add("tab-col-highlighted");
        element.style.setProperty("font-weight", HIGHLIGHT_STYLES.cellFontWeight, "important");
      }

      applyElementStyles(element, column.style);

      const cellMeta = cellMetadataMap[rowIdx]?.[field];
      if (cellMeta) {
        if (
          tournamentCutRowStyling &&
          rankFieldForCut &&
          field === rankFieldForCut &&
          cellMeta.backgroundColor != null
        ) {
          const { backgroundColor: _bg, ...rest } = cellMeta;
          if (Object.keys(rest).length > 0) applyCellMeta(element, rest);
        } else {
          applyCellMeta(element, cellMeta);
        }
      }

      if (settings.enableHeatMap && heatmapRanges[field]) {
        const num = toFiniteNumber(value);
        if (num !== null) {
          const range = heatmapRanges[field];
          const heatmapColor = getHeatMapColor(num, range.min, range.max);
          element.style.setProperty("background-color", heatmapColor, "important");
        }
      }

      // Decimal formatting (re-apply at render in case raw value came through)
      const decimalPlaces = decimalPlacesMap[field];
      let formatted: string | number | null = null;
      if (decimalPlaces !== undefined && decimalPlaces >= 0) {
        const num = toFiniteNumber(value);
        if (num !== null) formatted = num.toFixed(decimalPlaces);
      }
      const displayValue = String(
        formatted ?? (value === null || value === undefined ? "" : value),
      );

      // player_initials column → colored circle with player initial
      if (field === "player_initials") {
        const playerName = rowData["player_name"];
        if (
          typeof playerName === "string" &&
          value !== null &&
          value !== undefined &&
          value !== ""
        ) {
          const normalized = playerName.trim();
          const playerColors = getPlayerColorMap();
          const teamColors = getTeamColorMap();
          let color =
            playerColors[normalized] ||
            teamColors[normalized] ||
            getTeamColor(normalized, { league: settings.teamColorLeague });
          if (!color || color === "#888") color = hashColor(normalized);
          pinPositionCell(element);
          return positionClipHtml(displayValue, color, true);
        }
      }

      // position columns → team-colored clip badge (flat left, half-circle right)
      if (
        isRankPositionColumn(field, contextGroupIndex, contextColumnIndex, settings) &&
        !settings.disablePositionCircle &&
        displayValue !== ""
      ) {
        const teamName = resolvePositionTeamName(
          field,
          rowData,
          rowIdx,
          data,
          columnOrder,
          teamField,
          cell,
        );
        if (teamName) {
          const normalized = teamName.trim();
          const color = getTeamColor(normalized, { league: settings.teamColorLeague });
          pinPositionCell(element);
          return positionClipHtml(displayValue, color, false);
        }
      }

      return displayValue;
    };

  // ----- Build Tabulator column definitions -----
  let tabulatorColumns: ColumnDefinition[] = [];

  if (!hasGroupTitles) {
    columnsForBuild.forEach((group, groupIndex) => {
      if (!Array.isArray(group.columns)) return;
      const groupFrozen = group.frozen === "left" || group.frozen === "right" ? group.frozen : null;
      const hasPerColumnFrozen = (group.columns ?? []).some(
        (c) => c.frozen === "left" || c.frozen === "right",
      );
      const isHighlighted = group.highlighted === true;
      group.columns.forEach((column, columnIndex) => {
        const info = columnLookup[`${groupIndex}-${columnIndex}`];
        if (!info) return;
        const def = buildColumnDefinition(
          column,
          info,
          isHighlighted,
          groupIndex,
          columnIndex,
          settings,
          isCompactLayout,
          transformedData,
          makeFormatter(column, info, isHighlighted, groupIndex, columnIndex),
        );
        const colFrozen = column.frozen === "left" || column.frozen === "right" ? column.frozen : null;
        if (hasPerColumnFrozen) {
          if (colFrozen) (def as { frozen?: string }).frozen = colFrozen;
        } else if (groupFrozen) {
          (def as { frozen?: string }).frozen = groupFrozen;
        }
        tabulatorColumns.push(def);
      });
    });
  } else {
    tabulatorColumns = columnsForBuild
      .map((group, groupIndex) => {
        if (!Array.isArray(group.columns)) return null;
        const groupFrozen =
          group.frozen === "left" || group.frozen === "right" ? group.frozen : null;
        const hasPerColumnFrozen = (group.columns ?? []).some(
          (c) => c.frozen === "left" || c.frozen === "right",
        );
        const isHighlighted = group.highlighted === true;
        let groupCssClass = group.cssClass ?? "";
        if (isHighlighted) groupCssClass = (groupCssClass + " tab-group-highlighted").trim();
        const childDefs = group.columns
          .map((column, columnIndex) => {
            const info = columnLookup[`${groupIndex}-${columnIndex}`];
            if (!info) return null;
            const def = buildColumnDefinition(
              column,
              info,
              isHighlighted,
              groupIndex,
              columnIndex,
              settings,
              isCompactLayout,
              transformedData,
              makeFormatter(column, info, isHighlighted, info.groupIndex, info.columnIndex),
              useStripedColumnGroups ? groupIndex : null,
            );
            const colFrozen = column.frozen === "left" || column.frozen === "right" ? column.frozen : null;
            if (hasPerColumnFrozen && colFrozen) {
              (def as { frozen?: string }).frozen = colFrozen;
            }
            return def;
          })
          .filter((c): c is ColumnDefinition => c !== null);
        const groupDef: ColumnDefinition = {
          title: group.title ?? "",
          headerHozAlign: "center",
          cssClass: groupCssClass || undefined,
          columns: childDefs,
        };
        if (groupFrozen && !hasPerColumnFrozen) (groupDef as { frozen?: unknown }).frozen = groupFrozen;
        return groupDef;
      })
      .filter((g): g is ColumnDefinition => g !== null);
  }

  if (!tabulatorColumns.length) {
    console.warn("[DataTable] No Tabulator column definitions");
    return null;
  }

  // Initial sort
  const initialSort = data.default_sort
    ? [
        {
          column: data.default_sort.field,
          dir: data.default_sort.dir ?? "desc",
        } as const,
      ]
    : undefined;

  // Team colors keyed by name — never by rank index in the # column.
  if (!settings.disableTeamColorUpdate) {
    const teams = extractTeamNamesFromTablePayload(data);
    if (teams.length > 0) {
      const league = settings.teamColorLeague;
      if (isTeamVsTeamComparisonTable(data)) {
        ensureTeamColors(teams, league);
      } else if (settings.seedTeamColorsFromTable) {
        seedTeamColorsFromTablePayload(data, league);
      } else {
        updateTeamColorMap(teams, league);
      }
    }
  }

  const tabulatorOptions: Options = {
    data: transformedData,
    columns: tabulatorColumns,
    columnDefaults: {
      vertAlign: "middle",
    },
    layout: isCompactLayout ? "fitData" : "fitColumns",
    responsiveLayout: false,
    // Tabulator's ResizeTable observer + fitColumns can recurse on hover (containerWidth creeps).
    autoResize: false,
    pagination: false,
    movableColumns: false,
    height: "auto",
    rowHeight: 40,
    cssClass: [
      "ds-tabulator",
      settings.stripedRows ? "is-striped-rows" : null,
      useStripedColumnGroups ? "is-striped-column-groups" : null,
      tournamentCutRowStyling ? "is-tournament-cut-rows" : null,
      rawOptions.leagueNavigation ? "has-league-cell-navigation" : null,
    ]
      .filter(Boolean)
      .join(" "),
    columnHeaderVertAlign: "middle",
    ...(initialSort ? { initialSort } : {}),
    rowFormatter: (row: RowComponent) => {
      const rowData = row.getData() as RowObject;
      const rowElement = row.getElement();
      const separatorBefore = hasSemanticSeparator(rowData.__rowMeta);
      const styling = rowData.__rowMeta?.styling;
      if (styling) {
        const effectiveStyling = { ...styling };
        if (separatorBefore) {
          delete effectiveStyling.borderTop;
        }
        applyElementStyles(rowElement, effectiveStyling);
      }

      rowElement.classList.toggle("tab-row-separator-before", separatorBefore);

      if (tournamentCutRowStyling) {
        const cutMeta =
          rankFieldForCut != null
            ? cellMetadataMap[rowData.__rowIndex]?.[rankFieldForCut]
            : undefined;
        applyTournamentCutRowAccent(rowElement, cutMeta);
        return;
      }

      const metaAccent = rowData.__rowMeta?.rowAccentColor;
      if (typeof metaAccent === "string" && metaAccent.length > 0) {
        applyRowAccentWash(rowElement, metaAccent);
        return;
      }

      if (!settings.enableSpecialRowStyling) {
        rowElement.classList.remove("tab-row-accent");
        rowElement.style.removeProperty("--row-accent-color");
        rowElement.style.removeProperty("--row-accent-overlay");
        return;
      }

      const teamValue = teamField ? rowData[teamField] : null;
      if (typeof teamValue === "string" && teamValue.length > 0) {
        const accentColor = getTeamColor(teamValue, { league: settings.teamColorLeague });
        if (accentColor) {
          // Row wash + left bar only when rank is not shown as a position clip.
          if (settings.disablePositionCircle) {
            applyRowAccentWash(rowElement, accentColor);
          } else {
            rowElement.classList.remove("tab-row-accent");
            rowElement.style.removeProperty("--row-accent-color");
            rowElement.style.removeProperty("--row-accent-overlay");
          }
        }
      } else {
        rowElement.classList.remove("tab-row-accent");
        rowElement.style.removeProperty("--row-accent-color");
        rowElement.style.removeProperty("--row-accent-overlay");
      }
    },
  };

  const tabulator = new Tabulator(container, tabulatorOptions);

  const leagueNavigation = rawOptions.leagueNavigation;
  if (leagueNavigation) {
    const navCtx: LeagueNavContext = {
      season: leagueNavigation.season,
      league: leagueNavigation.league,
      defaultWeek: leagueNavigation.defaultWeek,
    };
    tabulator.on("cellClick", (_e, cell) => {
      const field = cell.getField();
      if (!field) return;
      const groupIndex = groupIndexFromCellElement(cell.getElement());
      const rowData = cell.getRow().getData() as RowObject;
      const team = typeof rowData.team === "string" ? rowData.team : null;
      const path = resolveLeagueCellNavPath(field, groupIndex, team, data.columns, navCtx);
      if (path) leagueNavigation.onNavigate(path);
    });
  }

  // Post-render: highlight class application + hide empty group header rows
  tabulator.on("tableBuilt", () => {
    runPostRender(
      container,
      data,
      hasGroupTitles,
      useStripedColumnGroups,
      settings.tooltips,
    );
  });
  tabulator.on("dataProcessed", () => {
    runPostRender(
      container,
      data,
      hasGroupTitles,
      useStripedColumnGroups,
      settings.tooltips,
    );
  });

  return {
    tabulator,
    destroy: () => {
      try {
        tabulator.destroy();
      } catch {
        /* swallow — Tabulator throws if container is detached */
      }
      container.replaceChildren();
    },
  };
}

// ─── helpers ───────────────────────────────────────────────────────────────

function formatDecimal(cell: unknown, decimalPlaces: number): unknown {
  const num = toFiniteNumber(cell);
  if (num === null) return cell;
  return num.toFixed(decimalPlaces);
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed === "" || trimmed === "null" || trimmed === "undefined" || trimmed === "NaN") {
      return null;
    }
    const parsed = parseFloat(trimmed);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

const TOURNAMENT_CUT_INSIDE = new Set(["#cfead6", "#e6f4ea"]);
const TOURNAMENT_CUT_ON = new Set(["#ffe8a1"]);

/** Einzeldurchschnitte-style row wash: saturated bar + 12% gradient from the same accent. */
function applyRowAccentWash(rowElement: HTMLElement, accentColor: string): void {
  rowElement.classList.remove("tab-row-accent", "tab-row-accent--outside-cut");
  rowElement.style.removeProperty("--row-accent-color");
  rowElement.style.removeProperty("--row-accent-overlay");
  rowElement.classList.add("tab-row-accent");
  rowElement.style.setProperty("--row-accent-color", accentColor);
  rowElement.style.setProperty("--row-accent-overlay", toRgba(accentColor, 0.12));
}

function applyTournamentCutRowAccent(
  rowElement: HTMLElement,
  meta: CellMetaStyles | undefined,
): void {
  const bg = meta?.backgroundColor;
  if (bg == null || bg === "") {
    applyRowAccentWash(rowElement, TOURNAMENT_CUT_ROW_COLORS.outside);
    return;
  }
  const norm = String(bg).trim().toLowerCase();
  if (TOURNAMENT_CUT_INSIDE.has(norm)) {
    applyRowAccentWash(rowElement, TOURNAMENT_CUT_ROW_COLORS.inside);
    return;
  }
  if (TOURNAMENT_CUT_ON.has(norm)) {
    applyRowAccentWash(rowElement, TOURNAMENT_CUT_ROW_COLORS.on);
    return;
  }
  applyRowAccentWash(rowElement, TOURNAMENT_CUT_ROW_COLORS.outside);
}

function applyCellMeta(element: HTMLElement, meta: CellMetaStyles): void {
  if (meta.backgroundColor !== undefined && meta.backgroundColor !== null) {
    element.style.setProperty("background-color", String(meta.backgroundColor), "important");
  }
  Object.entries(meta).forEach(([prop, value]) => {
    if (prop !== "backgroundColor" && value !== undefined && value !== null) {
      (element.style as unknown as Record<string, string | number>)[prop] = value;
    }
  });
}

function pinPositionCell(cellEl: HTMLElement): void {
  cellEl.classList.add("tab-position-cell");
  cellEl.style.setProperty("text-align", "left", "important");
  cellEl.style.setProperty("align-items", "center", "important");
  cellEl.style.setProperty("justify-content", "flex-start", "important");
  cellEl.style.setProperty("padding-top", "8px", "important");
  cellEl.style.setProperty("padding-bottom", "8px", "important");
  cellEl.style.setProperty("padding-left", "0", "important");
  cellEl.style.setProperty("padding-right", "0", "important");
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** HTML badges — avoids Tabulator 6 hover lookup issues with detached DOM nodes (esp. frozen cols). */
function positionClipHtml(value: string, color: string, initials: boolean): string {
  const clipClass = initials ? "tab-position-clip tab-position-clip--initials" : "tab-position-clip";
  const style = initials
    ? `--clip-color: ${color}; background-color: ${color} !important`
    : `--clip-color: ${color}`;
  return `<span class="${clipClass}" style="${style}"><span class="tab-position-clip__value">${escapeHtml(value)}</span></span>`;
}

function hashColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash % 360);
  return `hsl(${hue}, 70%, 50%)`;
}

function resolvePositionTeamName(
  field: string,
  rowData: RowObject,
  rowIdx: number,
  data: TableData,
  columnOrder: FlatColumnInfo[],
  teamField: string | null,
  cell: CellComponent,
): string | null {
  if (field === "team_position") {
    const v = rowData["team_name"] ?? (teamField ? rowData[teamField] : null);
    return typeof v === "string" ? v : null;
  }
  if (field === "opponent_position") {
    const opponentNameIndex = columnOrder.findIndex((ci) => ci.field === "opponent_name");
    if (
      opponentNameIndex >= 0 &&
      rowIdx >= 0 &&
      Array.isArray(data.data[rowIdx]) &&
      opponentNameIndex < (data.data[rowIdx] as unknown[]).length
    ) {
      const v = (data.data[rowIdx] as unknown[])[opponentNameIndex];
      return typeof v === "string" ? v : null;
    }
    if (typeof rowData["opponent_name"] === "string") return rowData["opponent_name"] as string;
    try {
      const opponentCell = cell.getRow().getCell("opponent_name");
      if (opponentCell) {
        const v = opponentCell.getValue();
        return typeof v === "string" ? v : null;
      }
    } catch {
      /* cell might not be rendered yet */
    }
    return null;
  }
  // Fallback: first column of first group → resolve against player_name or team field.
  const v = rowData["player_name"] ?? (teamField ? rowData[teamField] : null);
  return typeof v === "string" ? v : null;
}

function isRankPositionColumn(
  field: string,
  groupIndex: number,
  columnIndex: number,
  settings: Required<
    Omit<
      DataTableOptions,
      | "stripedColumnGroups"
      | "columnGroupStripeVariant"
      | "leagueNavigation"
      | "teamVsTeamMetric"
      | "tournamentCutRowStyling"
      | "playerColorOrder"
      | "performanceTeamName"
    >
  >,
): boolean {
  return (
    field === "pos" ||
    field === "team_position" ||
    field === "opponent_position" ||
    (!settings.disablePositionCircle && groupIndex === 0 && columnIndex === 0)
  );
}

function buildColumnDefinition(
  column: ColumnDef,
  info: FlatColumnInfo,
  isHighlighted: boolean,
  groupIndex: number,
  columnIndex: number,
  settings: Required<
    Omit<
      DataTableOptions,
      | "stripedColumnGroups"
      | "columnGroupStripeVariant"
      | "leagueNavigation"
      | "teamVsTeamMetric"
      | "tournamentCutRowStyling"
      | "playerColorOrder"
      | "performanceTeamName"
    >
  >,
  isCompactLayout: boolean,
  transformedData: RowObject[],
  formatter: (cell: CellComponent) => string | HTMLElement,
  stripeGroupIndex: number | null = null,
): ColumnDefinition {
  const headerAlign = column.align ?? "center";
  const sample = transformedData.length ? transformedData[0][info.field] : null;
  const isNumberColumn = typeof sample === "number";
  const isStringNumber =
    typeof sample === "string" &&
    !Number.isNaN(parseFloat(sample)) &&
    Number.isFinite(parseFloat(sample));

  const cssClasses: string[] = [];
  if (column.align === "right") cssClasses.push("text-end");
  else if (column.align === "left") cssClasses.push("text-start");
  else cssClasses.push("text-center");
  if (isHighlighted) cssClasses.push("tab-col-highlighted");
  if (column.cssClass) cssClasses.push(column.cssClass);
  if (stripeGroupIndex !== null) cssClasses.push("col-group-" + stripeGroupIndex);
  if (isRankPositionColumn(info.field, groupIndex, columnIndex, settings)) {
    cssClasses.push("tab-position-col");
  }
  // Backend may send header-only classes; Tabulator 6 applies cssClass to headers and cells.
  if (column.headerClass) cssClasses.push(column.headerClass);

  const def: ColumnDefinition = {
    title: column.title ?? "",
    field: info.field,
    hozAlign: headerAlign,
    headerHozAlign: headerAlign,
    vertAlign: "middle",
    headerSort: column.sortable !== false,
    sorter:
      column.sortable === false
        ? undefined
        : isNumberColumn || isStringNumber
          ? "number"
          : "string",
    formatter,
    cssClass: cssClasses.join(" ") || undefined,
  };

  const minWidth = parseColumnWidth(column.width) ?? 100;
  if (isCompactLayout) {
    def.minWidth = minWidth;
    def.widthGrow = 0;
  } else {
    def.minWidth = minWidth;
    const isTextColumn = !isNumberColumn && !isStringNumber;
    const isTeamColumn = !!info.field && /team|player|name/.test(info.field);
    def.widthGrow = isTeamColumn ? 3 : isTextColumn ? 2 : 1;
  }

  return def;
}

function findColumnMeta(
  data: TableData,
  field: string,
): { tooltip?: string } | null {
  for (const group of data.columns) {
    for (const col of group.columns ?? []) {
      if (col.field === field) {
        const tooltip =
          col.tooltip !== undefined && col.tooltip !== null && col.tooltip !== ""
            ? col.tooltip
            : undefined;
        return { tooltip };
      }
    }
  }
  return null;
}

/** Native title tooltips — Tabulator column tooltip/headerTooltip breaks hover on 6.3+ with frozen cols. */
function applyNativeTooltips(container: HTMLElement, data: TableData): void {
  container.querySelectorAll<HTMLElement>(".tabulator-col[tabulator-field]").forEach((colEl) => {
    const field = colEl.getAttribute("tabulator-field");
    if (!field) return;
    const titleEl = colEl.querySelector(".tabulator-col-title");
    const titleText = titleEl?.textContent?.trim() ?? "";
    const tooltipText = findColumnMeta(data, field)?.tooltip ?? titleText;
    if (!tooltipText) return;
    colEl.setAttribute("title", tooltipText);
    titleEl?.setAttribute("title", tooltipText);
  });

  container.querySelectorAll<HTMLElement>(".tabulator-cell[tabulator-field]").forEach((cellEl) => {
    const text = cellEl.textContent?.trim() ?? "";
    if (text) cellEl.setAttribute("title", text);
  });
}

function ensureTabulatorStripeClasses(
  container: HTMLElement,
  useStripedColumnGroups: boolean,
): HTMLElement {
  const root = container.classList.contains("tabulator")
    ? container
    : (container.querySelector(".tabulator") as HTMLElement | null) ?? container;
  root.classList.add("ds-tabulator");
  if (useStripedColumnGroups) {
    root.classList.add("is-striped-column-groups");
  }
  return root;
}

function stripVerticalColumnDividers(container: HTMLElement): void {
  container
    .querySelectorAll<HTMLElement>(
      ".tab-position-cell, .tab-position-col, .tabulator-cell, .tabulator-col, .tabulator-col-group",
    )
    .forEach((el) => {
      el.style.setProperty("border-right", "none", "important");
      el.style.setProperty("border-left", "none", "important");
      if (el.classList.contains("tab-position-cell") || el.classList.contains("tab-position-col")) {
        el.style.setProperty("box-shadow", "none", "important");
      }
    });
}

function runPostRender(
  container: HTMLElement,
  data: TableData,
  hasGroupTitles: boolean,
  useStripedColumnGroups: boolean,
  enableTooltips: boolean,
): void {
  // Two RAFs to let Tabulator finish DOM mounting of headers
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const root = ensureTabulatorStripeClasses(container, useStripedColumnGroups);
      root.style.setProperty("--highlight-header-bg", HIGHLIGHT_STYLES.headerBackgroundColor);
      container.style.setProperty("--highlight-cell-bg", HIGHLIGHT_STYLES.cellBackgroundColor);
      container.style.setProperty("--highlight-header-weight", HIGHLIGHT_STYLES.headerFontWeight);
      container.style.setProperty("--highlight-cell-weight", HIGHLIGHT_STYLES.cellFontWeight);

      const highlightedFields = new Set<string>();
      data.columns.forEach((group) => {
        if (group.highlighted === true && group.columns) {
          group.columns.forEach((c) => {
            if (c.field) highlightedFields.add(c.field);
          });
        }
      });

      // Hide empty group header row when no group titles
      if (!hasGroupTitles) {
        const headerRows = container.querySelector(".tabulator-header-rows");
        if (headerRows) {
          headerRows.querySelectorAll<HTMLElement>(".tabulator-header-row").forEach((row) => {
            const colGroups = row.querySelectorAll(".tabulator-col-group");
            if (colGroups.length === 0) return;
            let allEmpty = true;
            colGroups.forEach((cg) => {
              const t = cg.querySelector(".tabulator-col-group-title")?.textContent?.trim() ?? "";
              if (t !== "") allEmpty = false;
            });
            if (allEmpty) {
              row.style.setProperty("display", "none", "important");
              row.style.setProperty("height", "0", "important");
              row.style.setProperty("min-height", "0", "important");
            }
          });
        }
      }

      if (highlightedFields.size > 0) {
        container
          .querySelectorAll<HTMLElement>(".tabulator-col[tabulator-field]")
          .forEach((col) => {
            const f = col.getAttribute("tabulator-field");
            if (f && highlightedFields.has(f)) {
              col.classList.add("tab-col-highlighted");
            }
          });
        container
          .querySelectorAll<HTMLElement>(".tabulator-cell[tabulator-field]")
          .forEach((cell) => {
            const f = cell.getAttribute("tabulator-field");
            if (f && highlightedFields.has(f)) {
              cell.classList.add("tab-col-highlighted");
            }
          });
      }

      stripVerticalColumnDividers(container);

      if (enableTooltips) {
        applyNativeTooltips(container, data);
      }
    });
  });
}
