import { useEffect, useId, useMemo, useRef } from "react";
import type { CSSProperties } from "react";
import { TabulatorFull as TabulatorConstructor } from "tabulator-tables";
import type { CellComponent, ColumnDefinition, Options } from "tabulator-tables";
import "./TabulatorTable.css";
import type { TableColumnGroup, TableData } from "../types";
import { lookupTeamColor, resolveTeamColorForRow } from "../lib/teamColors";
import {
  DEFAULT_STRIPE_PALETTE,
  injectStripeCss,
  type StripeCssOptions,
} from "../lib/stripeCss";
import {
  applyLegacyStyle,
  decimalsOrString,
  flattenColumnOrder,
  mapCellMetadataByField,
  mergeColumnStyleOnto,
  normalizeDefaultSort,
  tableSchemaSignature,
} from "../lib/tableMeta";
import { THEME } from "../lib/theme";

type Props = {
  table: TableData;
  cellStyle?: (value: unknown, col: string, row: Record<string, unknown>) => CSSProperties | undefined;
  cellTooltip?: (value: unknown, col: string, row: Record<string, unknown>) => string;
  teamColors?: Record<string, string>;
  useTeamColorFirstColumn?: boolean;
  limit?: number;
  paginate?: boolean;
  /** Extra frozen columns from the left when JSON does not use `frozen` groups (rare). */
  frozenColumns?: number;
  /** Row zebra; also respects `config.stripRows === false` */
  horizontalStriping?: boolean;
  /**
   * When `config.stripedColGroups` is omitted, drives vertical stripes:
   * `group` matches legacy `stripedColGroups`; `column` stripes by flat column index.
   * Default `none` so tables without striping metadata match legacy Flask defaults.
   */
  verticalStripeMode?: "none" | "column" | "group";
  maxHeight?: string;
};

type FlatCol = {
  field: string;
  title: string;
  align?: "left" | "center" | "right";
  sortable?: boolean;
  width?: string;
  decimal_places?: number;
  tooltip?: string;
  style?: Record<string, string>;
  cssClass?: string;
  headerClass?: string;
  groupIndex: number;
  colInGroup: number;
  frozenGroup: boolean;
  groupHighlighted: boolean;
  groupCssClass?: string;
};

type LegacyDecorModel = {
  hasGroupTitles: boolean;
  highlightedFields: Set<string>;
  highlightedGroupTitles: Set<string>;
  applyStripedGroupClasses: boolean;
};

function flattenColumns(groups: TableColumnGroup[]): FlatCol[] {
  return groups.flatMap((g, groupIndex) =>
    g.columns.map((c, colInGroup) => ({
      field: c.field,
      title: c.title?.trim() ? c.title : c.field,
      align: c.align,
      sortable: c.sortable,
      width: c.width,
      decimal_places: c.decimal_places,
      tooltip: c.tooltip,
      style: c.style,
      cssClass: c.cssClass,
      headerClass: c.headerClass,
      groupIndex,
      colInGroup,
      frozenGroup: g.frozen === "left",
      groupHighlighted: g.highlighted === true,
      groupCssClass: g.cssClass,
    })),
  );
}

function hasGroupHeaders(groups: TableColumnGroup[]): boolean {
  return groups.length > 1 || groups.some((g) => g.title && g.title.trim().length > 0);
}

function parseWidthPx(raw: string | undefined): number | undefined {
  if (!raw) return undefined;
  const n = parseInt(String(raw).replace("px", "").trim(), 10);
  return Number.isNaN(n) ? undefined : n;
}

function firstColumnDotColor(
  row: Record<string, unknown>,
  teamColors: Record<string, string> | undefined,
  firstField: string,
): string {
  const fromTeamFields = resolveTeamColorForRow(row, teamColors);
  if (fromTeamFields) return fromTeamFields;
  const raw = row[firstField];
  if (typeof raw === "string" && raw.trim()) {
    const looksLikeRank = /^\d+$/.test(raw.trim());
    if (!looksLikeRank && teamColors) {
      const c = lookupTeamColor(teamColors, raw);
      if (c) return c;
    }
  }
  return THEME.fallback.teamDot;
}

function applyDomStyle(el: HTMLElement, style: CSSProperties | undefined) {
  if (!style) return;
  Object.assign(el.style, style);
}

function buildLegacyDecorModel(
  groups: TableColumnGroup[],
  applyStripedGroupClasses: boolean,
): LegacyDecorModel {
  const highlightedFields = new Set<string>();
  const highlightedGroupTitles = new Set<string>();

  groups.forEach((g) => {
    if (g.highlighted === true) {
      highlightedGroupTitles.add(g.title || "");
      g.columns.forEach((c) => {
        if (c.field) highlightedFields.add(c.field);
      });
    }
  });

  return {
    hasGroupTitles: hasGroupHeaders(groups),
    highlightedFields,
    highlightedGroupTitles,
    applyStripedGroupClasses,
  };
}

function hideEmptyGroupHeaderRows(root: HTMLElement) {
  const header = root.querySelector(".tabulator-header");
  if (!header) return;
  const headerRows = header.querySelector(".tabulator-header-rows");
  if (!headerRows) return;
  const rows = headerRows.querySelectorAll(".tabulator-header-row");
  rows.forEach((row) => {
    const colGroups = row.querySelectorAll(".tabulator-col-group");
    if (colGroups.length === 0) return;
    const hasAnyTitle = Array.from(colGroups).some((colGroup) => {
      const titleEl = colGroup.querySelector(".tabulator-col-group-title, .tabulator-col-title");
      return !!titleEl?.textContent?.trim();
    });
    if (!hasAnyTitle) {
      (row as HTMLElement).style.setProperty("display", "none", "important");
      (row as HTMLElement).style.setProperty("height", "0", "important");
      (row as HTMLElement).style.setProperty("min-height", "0", "important");
    }
  });
}

function ensureHeaderTooltips(root: HTMLElement, groups: TableColumnGroup[]) {
  const columns = root.querySelectorAll(".tabulator-col");
  columns.forEach((colElement) => {
    const el = colElement as HTMLElement;
    if (el.getAttribute("title")) return;
    const titleElement = el.querySelector(".tabulator-col-title") as HTMLElement | null;
    if (!titleElement) return;
    const titleText = titleElement.textContent?.trim() ?? "";
    if (!titleText) return;

    const field = el.getAttribute("tabulator-field");
    let tooltipText = titleText;
    if (field) {
      for (const group of groups) {
        for (const col of group.columns) {
          if (col.field === field) {
            if (col.tooltip && col.tooltip.trim()) tooltipText = col.tooltip;
            break;
          }
        }
      }
    }
    el.setAttribute("title", tooltipText);
    titleElement.setAttribute("title", tooltipText);
  });
}

function applyLegacyPostProcessing(
  root: HTMLElement,
  decor: LegacyDecorModel,
  groups: TableColumnGroup[],
) {
  const header = root.querySelector(".tabulator-header") as HTMLElement | null;
  if (!header) return;

  root.style.setProperty("--highlight-header-weight", "900");
  root.style.setProperty("--highlight-cell-weight", "700");
  root.style.setProperty("--highlight-header-bg", "var(--theme-highlight-header-bg)");

  header.style.setProperty("border-bottom", "none", "important");
  const headerContents = header.querySelector(".tabulator-header-contents") as HTMLElement | null;
  if (headerContents) headerContents.style.setProperty("border-bottom", "none", "important");
  const headers = header.querySelector(".tabulator-headers") as HTMLElement | null;
  if (headers) headers.style.setProperty("border-bottom", "none", "important");

  if (decor.applyStripedGroupClasses) {
    root.querySelectorAll(".tabulator-col-group").forEach((el, idx) => {
      el.classList.add(`col-group-${idx}`);
    });
  }

  if (!decor.hasGroupTitles) {
    hideEmptyGroupHeaderRows(root);
  }

  if (decor.highlightedFields.size > 0) {
    header.querySelectorAll(".tabulator-col-group").forEach((colGroup) => {
      const groupEl = colGroup as HTMLElement;
      const groupTitle = groupEl.getAttribute("aria-title") ?? "";
      const hasMarkedTitle = !!groupEl.querySelector('.tab-group-title[data-highlighted="true"]');
      if (hasMarkedTitle || decor.highlightedGroupTitles.has(groupTitle)) {
        groupEl.classList.add("tab-group-highlighted");
        groupEl.querySelectorAll(".tabulator-col").forEach((col) => {
          col.classList.add("tab-col-highlighted");
        });
      }
    });

    header.querySelectorAll(".tabulator-col[tabulator-field]").forEach((col) => {
      const field = col.getAttribute("tabulator-field");
      if (field && decor.highlightedFields.has(field)) {
        col.classList.add("tab-col-highlighted");
      }
    });

    root.querySelectorAll(".tabulator-row .tabulator-cell").forEach((cell) => {
      const field = cell.getAttribute("tabulator-field");
      if (field && decor.highlightedFields.has(field)) {
        cell.classList.add("tab-col-highlighted");
      }
    });
  }

  ensureHeaderTooltips(root, groups);
}

export default function TabulatorTable({
  table,
  cellStyle,
  cellTooltip,
  teamColors,
  useTeamColorFirstColumn = false,
  limit,
  paginate = true,
  frozenColumns = 0,
  horizontalStriping = false,
  verticalStripeMode = "none",
  maxHeight = "min(520px, 65vh)",
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const instanceRef = useRef<InstanceType<typeof TabulatorConstructor> | null>(null);
  const cellStyleRef = useRef(cellStyle);
  cellStyleRef.current = cellStyle;

  const reactId = useId();
  const stripeScopeClass = useMemo(
    () => `bowlyzer-stripe-${reactId.replace(/:/g, "")}`,
    [reactId],
  );

  const cfg = table.config;
  const isCompact = cfg?.compact === true;
  const stripeGroupsCfg = cfg?.stripedColGroups;
  const verticalEffective: "none" | "column" | "group" =
    verticalStripeMode === "none"
      ? "none"
      : stripeGroupsCfg === true
        ? "group"
        : stripeGroupsCfg === false
          ? "none"
          : verticalStripeMode;

  /** Legacy `table-striped` row striping */
  const rowStripedOk = cfg?.stripRows !== false;
  const horizontalStripingEffective = horizontalStriping && rowStripedOk;

  const flatColumns = useMemo(() => flattenColumns(table.columns), [table.columns]);
  const fieldOrder = useMemo(() => flatColumns.map((c) => c.field), [flatColumns]);
  const grouped = useMemo(() => hasGroupHeaders(table.columns), [table.columns]);

  const fieldToFlat = useMemo(
    () => new Map(flatColumns.map((c) => [c.field, c])),
    [flatColumns],
  );

  const cellMetaByField = useMemo(
    () => mapCellMetadataByField(table.cell_metadata, fieldOrder),
    [table.cell_metadata, fieldOrder],
  );

  const prevSchemaSigRef = useRef<string | null>(null);
  const prevLayoutSigRef = useRef<string>("");
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const cellRenderedBoundRef = useRef(false);
  const tableBuiltRef = useRef(false);
  const safeRedrawRef = useRef(() => {});

  const tablePayloadRef = useRef(table);
  const horizontalStripingRef = useRef(horizontalStripingEffective);
  const cellMetaByFieldRef = useRef(cellMetaByField);
  const fieldToFlatRef = useRef(fieldToFlat);
  tablePayloadRef.current = table;
  horizontalStripingRef.current = horizontalStripingEffective;
  cellMetaByFieldRef.current = cellMetaByField;
  fieldToFlatRef.current = fieldToFlat;

  const data = useMemo(() => {
    const rows = typeof limit === "number" ? table.rows.slice(0, limit) : table.rows;
    return rows.map((r, ri) => ({
      ...r,
      __rowIndex: ri,
    }));
  }, [table.rows, limit]);

  const sampleRow = data[0] as Record<string, unknown> | undefined;

  const defaultSort = useMemo(() => normalizeDefaultSort(cfg), [cfg]);

  const columns = useMemo(
    () =>
      buildTabulatorColumns({
        table,
        flatColumns,
        grouped,
        verticalEffective,
        useTeamColorFirstColumn,
        teamColors,
        cellTooltip,
        sampleRow,
        frozenColumns,
      }),
    [
      table,
      flatColumns,
      grouped,
      verticalEffective,
      useTeamColorFirstColumn,
      teamColors,
      cellTooltip,
      sampleRow,
      frozenColumns,
    ],
  );

  const stripeOptions: StripeCssOptions = useMemo(
    () => ({
      palette: DEFAULT_STRIPE_PALETTE,
      headerAlpha: isCompact ? 0.3 : 0.2,
      cellAlpha: 0.1,
    }),
    [isCompact],
  );

  const legacyDecor = useMemo(
    () => buildLegacyDecorModel(table.columns, verticalEffective === "group" && grouped),
    [table.columns, verticalEffective, grouped],
  );

  useEffect(() => {
    const shouldInject =
      verticalEffective === "group" &&
      grouped &&
      table.columns.length > 0;
    if (!shouldInject) {
      const styleId = `bowlyzer-stripes-css-${stripeScopeClass.replace(/[^\w-]/g, "")}`;
      document.getElementById(styleId)?.remove();
      return;
    }
    return injectStripeCss(stripeScopeClass, table.columns.length, stripeOptions);
  }, [verticalEffective, grouped, table.columns.length, stripeScopeClass, stripeOptions]);

  const schemaSig = useMemo(() => tableSchemaSignature(table), [table]);

  const initialSortTab = useMemo(
    () =>
      defaultSort?.field != null
        ? [{ column: defaultSort.field, dir: defaultSort.dir }]
        : undefined,
    [defaultSort],
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el || columns.length === 0) return;

    const layoutSig = `${maxHeight}|${isCompact ? "1" : "0"}|${paginate ? "1" : "0"}`;

    /**
     * Tabulator finishes `_create` async; `redraw` must run after layout/init guards clear.
     * Defer past microtasks + two animation frames (matches Tabulator's internal timing).
     */
    const scheduleRedraw = (): void => {
      queueMicrotask(() => {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            const inst = instanceRef.current;
            if (!inst || !tableBuiltRef.current) return;
            const mount = containerRef.current;
            if (!mount?.isConnected) return;
            const initialized = (inst as unknown as { initialized?: boolean }).initialized;
            if (initialized === false) return;
            try {
              inst.redraw(true);
            } catch {
              /* noop */
            }
          });
        });
      });
    };

    safeRedrawRef.current = scheduleRedraw;

    const attachResizeObserverOnce = (): void => {
      if (resizeObserverRef.current || !containerRef.current) return;
      resizeObserverRef.current = new ResizeObserver(() => {
        scheduleRedraw();
      });
      resizeObserverRef.current.observe(containerRef.current);
    };

    const rowFormatter: Options["rowFormatter"] = (row) => {
      const elt = row.getElement();
      if (horizontalStripingRef.current) {
        const pos = row.getPosition();
        if (typeof pos === "number" && pos % 2 === 1) {
          elt?.classList.add("bowlyzer-row-stripe");
        } else {
          elt?.classList.remove("bowlyzer-row-stripe");
        }
      } else {
        elt?.classList.remove("bowlyzer-row-stripe");
      }

      const rd = row.getData() as Record<string, unknown> & { __rowIndex?: number };
      const ri = typeof rd.__rowIndex === "number" ? rd.__rowIndex : -1;
      const meta = ri >= 0 ? tablePayloadRef.current.row_metadata?.[ri] : undefined;
      const styling =
        meta && typeof meta === "object" && meta !== null
          ? (meta as { styling?: Record<string, unknown> }).styling
          : undefined;
      if (styling && typeof styling === "object" && elt) {
        applyLegacyStyle(elt, styling as Record<string, unknown>);
      }
    };

    const onCellRendered = (cell: CellComponent) => {
      let td: HTMLElement | undefined;
      try {
        td = cell.getElement() ?? undefined;
        if (!td?.isConnected) return;
      } catch {
        return;
      }

      let field: string | undefined;
      try {
        field = cell.getField();
      } catch {
        return;
      }
      if (!field || field.startsWith("__")) return;

      let row: Record<string, unknown> & { __rowIndex?: number };
      try {
        row = cell.getRow().getData() as Record<string, unknown> & { __rowIndex?: number };
      } catch {
        return;
      }

      const ri = typeof row.__rowIndex === "number" ? row.__rowIndex : -1;
      let val: unknown;
      try {
        val = cell.getValue();
      } catch {
        return;
      }

      const flat = fieldToFlatRef.current.get(field);
      if (flat?.style) {
        mergeColumnStyleOnto(td, flat.style);
      }

      const colMetaStyles =
        ri >= 0 ? cellMetaByFieldRef.current.get(`${ri}:${field}`) : undefined;
      if (colMetaStyles && typeof colMetaStyles === "object") {
        applyLegacyStyle(td, colMetaStyles as Record<string, unknown>);
      }

      const fn = cellStyleRef.current;
      if (fn) {
        const st = fn(val, field, row);
        applyDomStyle(td, st);
      }
    };

    let tab = instanceRef.current;

    if (tab && prevLayoutSigRef.current !== "" && prevLayoutSigRef.current !== layoutSig) {
      tab.destroy();
      instanceRef.current = null;
      tab = null;
      tableBuiltRef.current = false;
      resizeObserverRef.current?.disconnect();
      resizeObserverRef.current = null;
    }

    const baseOptions = (): Partial<Options> => ({
      /**
       * Always `fitData`: column widths follow content + minWidth. `fitColumns` stretches
       * sparse tables to fill the row and shifts layout when switching to leagues with many
       * week columns (horizontal scroll); that reads as “wobbly”.
       */
      layout: "fitData",
      responsiveLayout: false,
      movableColumns: false,
      height: maxHeight,
      rowHeight: 38,
      placeholder: "No data",
      columnHeaderVertAlign: "middle",
      rowFormatter,
    });

    if (!tab) {
      const opts: Options = {
        ...baseOptions(),
        data,
        columns,
        pagination: paginate,
        paginationSize: 25,
        paginationSizeSelector: [10, 25, 50, 100],
        paginationCounter: "rows",
      } as Options;

      if (initialSortTab) {
        opts.initialSort = initialSortTab;
      }
      if (!paginate) {
        opts.pagination = false;
        delete opts.paginationSize;
        delete opts.paginationSizeSelector;
        delete opts.paginationCounter;
      }

      tableBuiltRef.current = false;

      tab = new TabulatorConstructor(el, opts);
      instanceRef.current = tab;

      prevLayoutSigRef.current = layoutSig;

      tab.on("cellRendered" as never, onCellRendered as never);
      cellRenderedBoundRef.current = true;

      prevSchemaSigRef.current = schemaSig;

      tab.on("tableBuilt", () => {
        tableBuiltRef.current = true;
        attachResizeObserverOnce();
        if (containerRef.current) {
          applyLegacyPostProcessing(containerRef.current, legacyDecor, table.columns);
        }
        scheduleRedraw();
      });
    } else {
      /** Tabulator 6 has no `setOption`; height/layout etc. reload only when `layoutSig` forces recreate above. */
      const schemaChanged = prevSchemaSigRef.current !== schemaSig;
      if (schemaChanged) {
        prevSchemaSigRef.current = schemaSig;
        tab.setColumns(columns);
      }

      void tab.replaceData(data).then(() => {
        if (!instanceRef.current || !tableBuiltRef.current) return;
        if (schemaChanged && initialSortTab?.[0]?.column != null && initialSortTab?.[0]?.dir != null) {
          instanceRef.current.setSort(initialSortTab as NonNullable<Options["initialSort"]>);
        }
        if (containerRef.current) {
          applyLegacyPostProcessing(containerRef.current, legacyDecor, table.columns);
        }
        scheduleRedraw();
      });
    }
  }, [columns, data, schemaSig, isCompact, maxHeight, paginate, initialSortTab, legacyDecor, table.columns]);

  /** Row striping reads refs in `rowFormatter`; repaint when the toggle changes (table must be built). */
  useEffect(() => {
    horizontalStripingRef.current = horizontalStripingEffective;
    safeRedrawRef.current();
  }, [horizontalStripingEffective]);

  useEffect(
    () => () => {
      resizeObserverRef.current?.disconnect();
      resizeObserverRef.current = null;
      cellRenderedBoundRef.current = false;
      tableBuiltRef.current = false;
      prevLayoutSigRef.current = "";
      instanceRef.current?.destroy();
      instanceRef.current = null;
      prevSchemaSigRef.current = null;
      safeRedrawRef.current = () => {};
    },
    [],
  );

  return (
    <div
      className={`tabulatorTableWrap ${stripeScopeClass} ${verticalEffective !== "none" ? "vertical-stripe-enabled" : ""}`}
    >
      <div
        ref={containerRef}
        id={`bowlyzer-tab-${reactId.replace(/:/g, "")}`}
        className="tabulatorMount"
      />
    </div>
  );
}

function buildTabulatorColumns(args: {
  table: TableData;
  flatColumns: FlatCol[];
  grouped: boolean;
  verticalEffective: "none" | "column" | "group";
  useTeamColorFirstColumn: boolean;
  teamColors?: Record<string, string>;
  cellTooltip?: (value: unknown, col: string, row: Record<string, unknown>) => string;
  sampleRow?: Record<string, unknown>;
  frozenColumns: number;
}): ColumnDefinition[] {
  const {
    table,
    flatColumns,
    grouped,
    verticalEffective,
    useTeamColorFirstColumn,
    teamColors,
    cellTooltip,
    sampleRow,
    frozenColumns,
  } = args;

  const firstField = flatColumns[0]?.field ?? "";
  const flatOrder = flattenColumnOrder(table.columns);

  const leafCol = (col: FlatCol, flatIdx: number): ColumnDefinition => {
    const freezeLeaf =
      col.frozenGroup ||
      (!grouped && frozenColumns > 0 && flatIdx < frozenColumns);

    const useGroupStripeClass =
      verticalEffective === "group" && grouped && col.groupIndex >= 0;
    const stripeClass = useGroupStripeClass ? `col-group-${col.groupIndex}` : "";

    let cssParts: string[] = [];
    if (col.groupHighlighted) cssParts.push("tab-col-highlighted");
    if (col.cssClass) {
      const normalized =
        verticalEffective === "none"
          ? col.cssClass.replace(/\bcol-group-\d+\b/g, "").replace(/\s+/g, " ").trim()
          : col.cssClass;
      if (normalized) cssParts.push(normalized);
    }
    if (stripeClass) cssParts.push(stripeClass);
    if (verticalEffective === "column" && flatIdx % 2 === 1) {
      cssParts.push("col-stripe-odd");
    }

    const colWidth = parseWidthPx(col.width) ?? 100;

    const sampleVal = sampleRow?.[col.field];
    const isNumberColumn = typeof sampleVal === "number";
    const isStringNumber =
      typeof sampleVal === "string" &&
      !Number.isNaN(parseFloat(sampleVal)) &&
      String(sampleVal).trim() !== "" &&
      Number.isFinite(parseFloat(sampleVal));

    if (col.headerClass) {
      const normalized =
        verticalEffective === "none"
          ? col.headerClass.replace(/\bcol-group-\d+\b/g, "").replace(/\s+/g, " ").trim()
          : col.headerClass;
      if (normalized) cssParts.push(normalized);
    }

    const def: ColumnDefinition = {
      title: col.title,
      field: col.field,
      frozen: grouped ? undefined : !!freezeLeaf,
      hozAlign: col.align ?? "center",
      headerHozAlign: "center",
      headerSort: col.sortable !== false,
      sorter:
        col.sortable === false
          ? undefined
          : isNumberColumn || isStringNumber
            ? "number"
            : "string",
      /** Tabulator 6: `cssClass` applies to header and cells — `headerClass` alone is rejected. */
      cssClass: cssParts.join(" ").trim() || undefined,
      headerTooltip: col.tooltip ? col.tooltip : undefined,
      resizable: true,
      minWidth: colWidth,
      /** With `fitData`, extra panel width must not flex columns (`fitColumns` + grow caused jump between leagues). */
      widthGrow: 0,
      /**
       * Never default to `tooltip: true`: Tabulator attaches hover tracking (`track`) per cell and
       * resolves the row on pointer movement — lookup spam + “Event Target Lookup Error” when the
       * internal row map is briefly out of sync (React updates / redraw).
       */
      tooltip: cellTooltip
        ? ((event: MouseEvent, c: CellComponent) => {
            void event;
            try {
              const row = c.getRow().getData() as Record<string, unknown>;
              return cellTooltip(c.getValue(), c.getField(), row);
            } catch {
              return "";
            }
          })
        : false,
      formatter: (cell) => {
        const row = cell.getRow().getData() as Record<string, unknown>;
        const val = cell.getValue();
        const field = cell.getField();
        const dp =
          typeof col.decimal_places === "number" && !Number.isNaN(col.decimal_places)
            ? col.decimal_places
            : undefined;
        const text = decimalsOrString(val, dp);

        if (flatIdx === 0 && useTeamColorFirstColumn && field === firstField) {
          const wrap = document.createElement("span");
          wrap.className = "firstColWithTeamColor";
          const dot = document.createElement("span");
          dot.className = "teamColorDot";
          dot.style.backgroundColor = firstColumnDotColor(row, teamColors, firstField);
          dot.setAttribute("aria-hidden", "true");
          const label = document.createElement("span");
          label.textContent = text;
          wrap.append(dot, label);
          return wrap;
        }
        return text;
      },
    };
    return def;
  };

  if (!grouped) {
    return flatColumns.map((fc, i) => leafCol(fc, i));
  }

  return table.columns.map((group, gi) => {
    const useGroupStripeClass = verticalEffective === "group" && grouped;
    const groupStripeClass = useGroupStripeClass ? `col-group-${gi}` : "";
    const groupCssClass = [
      group.highlighted ? "tab-group-highlighted" : "",
      verticalEffective === "none"
        ? (group.cssClass ?? "").replace(/\bcol-group-\d+\b/g, "").replace(/\s+/g, " ").trim()
        : group.cssClass ?? "",
      groupStripeClass,
    ]
      .filter(Boolean)
      .join(" ")
      .trim();

    const cols = group.columns.map((c, colIdxInGroup) => {
      const flatIdx = flatOrder.findIndex(
        (e) => e.groupIndex === gi && e.columnIndex === colIdxInGroup,
      );
      const fc: FlatCol = {
        field: c.field,
        title: c.title?.trim() ? c.title : c.field,
        align: c.align,
        sortable: c.sortable,
        width: c.width,
        decimal_places: c.decimal_places,
        tooltip: c.tooltip,
        style: c.style,
        cssClass: c.cssClass,
        headerClass: c.headerClass,
        groupIndex: gi,
        colInGroup: colIdxInGroup,
        frozenGroup: group.frozen === "left",
        groupHighlighted: group.highlighted === true,
        groupCssClass: group.cssClass,
      };
      return leafCol(fc, flatIdx >= 0 ? flatIdx : colIdxInGroup);
    });

    const groupCols: ColumnDefinition = {
      title: group.title || "\u00a0",
      cssClass: groupCssClass || undefined,
      frozen: group.frozen === "left" || gi === 0 ? true : undefined,
      headerHozAlign: "center",
      columns: cols,
    };
    return groupCols;
  });
}
