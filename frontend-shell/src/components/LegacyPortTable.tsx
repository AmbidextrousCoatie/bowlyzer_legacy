import { useEffect, useId, useMemo, useRef } from "react";
import { TabulatorFull as TabulatorConstructor } from "tabulator-tables";
import type { ColumnDefinition, Options } from "tabulator-tables";
import type { TableColumnGroup, TableData } from "../types";
import { decimalsOrString, flattenColumnOrder, mapCellMetadataByField } from "../lib/tableMeta";
import { THEME } from "../lib/theme";
import "./LegacyPortTable.css";

type Props = {
  table: TableData;
};

function hasGroupHeaders(groups: TableColumnGroup[]): boolean {
  return groups.some((g) => (g.title ?? "").trim().length > 0);
}

function parseWidthPx(raw: string | undefined): number {
  if (!raw) return 100;
  const n = parseInt(String(raw).replace("px", "").trim(), 10);
  return Number.isNaN(n) ? 100 : n;
}

function applyMetaStyle(el: HTMLElement, style: Record<string, unknown>) {
  Object.entries(style).forEach(([k, v]) => {
    if (v !== undefined && v !== null) {
      el.style.setProperty(k, String(v));
    }
  });
}

function hideEmptyGroupHeaderRows(root: HTMLElement) {
  const header = root.querySelector(".tabulator-header");
  if (!header) return;
  const headerRows = header.querySelector(".tabulator-header-rows");
  if (!headerRows) return;
  const rows = headerRows.querySelectorAll(".tabulator-header-row");
  rows.forEach((row) => {
    const groups = row.querySelectorAll(".tabulator-col-group");
    if (groups.length === 0) return;
    const hasAnyTitle = Array.from(groups).some((g) => {
      const titleEl = g.querySelector(".tabulator-col-group-title, .tabulator-col-title");
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
  const cols = root.querySelectorAll(".tabulator-col");
  cols.forEach((col) => {
    const el = col as HTMLElement;
    if (el.getAttribute("title")) return;
    const titleEl = el.querySelector(".tabulator-col-title") as HTMLElement | null;
    const title = titleEl?.textContent?.trim() ?? "";
    if (!title) return;
    const field = el.getAttribute("tabulator-field");
    let tooltip = title;
    if (field) {
      for (const g of groups) {
        const found = g.columns.find((c) => c.field === field);
        if (found?.tooltip && found.tooltip.trim()) {
          tooltip = found.tooltip;
          break;
        }
      }
    }
    el.setAttribute("title", tooltip);
    titleEl?.setAttribute("title", tooltip);
  });
}

function applyLegacyPostProcessing(root: HTMLElement, groups: TableColumnGroup[], striped: boolean) {
  root.style.setProperty("--highlight-header-weight", "900");
  root.style.setProperty("--highlight-cell-weight", "700");
  root.style.setProperty("--highlight-header-bg", "rgba(0, 0, 0, 0.05)");
  const header = root.querySelector(".tabulator-header") as HTMLElement | null;
  if (header) {
    header.style.setProperty("border-bottom", "none", "important");
    const contents = header.querySelector(".tabulator-header-contents") as HTMLElement | null;
    contents?.style.setProperty("border-bottom", "none", "important");
    const headers = header.querySelector(".tabulator-headers") as HTMLElement | null;
    headers?.style.setProperty("border-bottom", "none", "important");
  }

  if (striped) {
    root.querySelectorAll(".tabulator-col-group").forEach((el, idx) => {
      el.classList.add(`col-group-${idx}`);
    });
  }
  if (!hasGroupHeaders(groups)) hideEmptyGroupHeaderRows(root);
  ensureHeaderTooltips(root, groups);
}

function applyHighlighting(root: HTMLElement, groups: TableColumnGroup[]) {
  const highlightedFields = new Set<string>();
  const highlightedGroupTitles = new Set<string>();
  groups.forEach((g) => {
    if (g.highlighted === true) {
      highlightedGroupTitles.add(g.title || "");
      g.columns.forEach((c) => c.field && highlightedFields.add(c.field));
    }
  });
  if (highlightedFields.size === 0) return;

  const header = root.querySelector(".tabulator-header");
  if (header) {
    header.querySelectorAll(".tabulator-col-group").forEach((colGroup) => {
      const groupEl = colGroup as HTMLElement;
      const ariaTitle = groupEl.getAttribute("aria-title") || "";
      if (highlightedGroupTitles.has(ariaTitle) || groupEl.querySelector(".tab-group-title[data-highlighted='true']")) {
        groupEl.classList.add("tab-group-highlighted");
        groupEl.querySelectorAll(".tabulator-col").forEach((col) => col.classList.add("tab-col-highlighted"));
      }
    });
    header.querySelectorAll(".tabulator-col[tabulator-field]").forEach((col) => {
      const field = col.getAttribute("tabulator-field");
      if (field && highlightedFields.has(field)) col.classList.add("tab-col-highlighted");
    });
  }

  root.querySelectorAll(".tabulator-row .tabulator-cell").forEach((cell) => {
    const field = cell.getAttribute("tabulator-field");
    if (field && highlightedFields.has(field)) cell.classList.add("tab-col-highlighted");
  });
}

function injectLegacyStripeCss(scopeClass: string, groupCount: number, compact: boolean): () => void {
  const styleId = `legacy-stripes-${scopeClass.replace(/[^\w-]/g, "")}`;
  let styleEl = document.getElementById(styleId) as HTMLStyleElement | null;
  if (!styleEl) {
    styleEl = document.createElement("style");
    styleEl.id = styleId;
    document.head.appendChild(styleEl);
  }
  const headerAlpha = compact ? 0.3 : 0.2;
  const cellAlpha = 0.1;
  const base = THEME.neutral.white;
  const accent = THEME.brand.teal700;
  const toRgba = (hex: string, a: number) => {
    const clean = hex.replace("#", "");
    const n = parseInt(clean, 16);
    const r = (n >> 16) & 255;
    const g = (n >> 8) & 255;
    const b = n & 255;
    return `rgba(${r}, ${g}, ${b}, ${a})`;
  };
  let css = "";
  for (let i = 0; i < groupCount; i++) {
    const color = i % 2 === 0 ? base : accent;
    const headerBg = toRgba(color, headerAlpha);
    const cellBg = toRgba(color, cellAlpha);
    css += `.${scopeClass} .tabulator-cell.col-group-${i}:not(.tabulator-frozen){background-color:${cellBg}!important;}\n`;
    css += `.${scopeClass} .tabulator-col.col-group-${i}:not(.tabulator-frozen){background-color:${headerBg}!important;}\n`;
    css += `.${scopeClass} .tabulator-col-group.col-group-${i}:not(.tabulator-frozen){background-color:${headerBg}!important;}\n`;
  }
  styleEl.textContent = css;
  return () => {
    document.getElementById(styleId)?.remove();
  };
}

export default function LegacyPortTable({ table }: Props) {
  const reactId = useId();
  const scopeClass = useMemo(() => `legacy-port-${reactId.replace(/:/g, "")}`, [reactId]);
  const mountRef = useRef<HTMLDivElement | null>(null);
  const instanceRef = useRef<InstanceType<typeof TabulatorConstructor> | null>(null);

  const grouped = useMemo(() => hasGroupHeaders(table.columns), [table.columns]);
  const flatOrder = useMemo(() => flattenColumnOrder(table.columns), [table.columns]);
  const fieldOrder = useMemo(() => flatOrder.map((c) => c.field), [flatOrder]);
  const cellMetaByField = useMemo(
    () => mapCellMetadataByField(table.cell_metadata ?? {}, fieldOrder),
    [table.cell_metadata, fieldOrder],
  );

  const transformedData = useMemo<Array<Record<string, unknown> & { __rowIndex: number }>>(
    () => table.rows.map((r, i) => ({ ...r, __rowIndex: i })),
    [table.rows],
  );

  const isCompact = table.config?.compact === true;
  const stripedGroups = table.config?.stripedColGroups === true;
  const rowStriping = table.config?.stripRows !== false;
  const hasGroupTitles = grouped;

  useEffect(() => {
    if (!stripedGroups || !table.columns.length) return;
    return injectLegacyStripeCss(scopeClass, table.columns.length, isCompact);
  }, [stripedGroups, table.columns.length, scopeClass, isCompact]);

  const columns = useMemo<ColumnDefinition[]>(() => {
    const buildLeaf = (
      group: TableColumnGroup,
      column: TableColumnGroup["columns"][number],
    ): ColumnDefinition => {
      const field = column.field;
      const sample = transformedData[0]?.[field];
      const isNumberColumn = typeof sample === "number";
      const isStringNumber =
        typeof sample === "string" &&
        !Number.isNaN(parseFloat(sample)) &&
        Number.isFinite(parseFloat(sample));
      const decimalPlaces =
        typeof column.decimal_places === "number" ? column.decimal_places : undefined;

      return {
        title: column.title || "",
        field,
        hozAlign: column.align ?? "center",
        headerHozAlign: column.align ?? "center",
        headerSort: column.sortable !== false,
        sorter: column.sortable === false ? undefined : isNumberColumn || isStringNumber ? "number" : "string",
        headerTooltip:
          typeof column.tooltip === "string" && column.tooltip.trim().length > 0
            ? column.tooltip
            : column.title || "",
        minWidth: parseWidthPx(column.width),
        widthGrow: isCompact ? 0 : 1,
        // legacy grouped freeze behavior: only parent group in grouped mode
        frozen: grouped ? undefined : group.frozen === "left" ? true : undefined,
        cssClass: [
          column.cssClass,
          stripedGroups ? `col-group-${table.columns.indexOf(group)}` : "",
          group.highlighted ? "tab-col-highlighted" : "",
        ]
          .filter(Boolean)
          .join(" "),
        formatter: (cell) => {
          const el = cell.getElement();
          const row = cell.getRow().getData() as Record<string, unknown> & { __rowIndex?: number };
          const rowIndex = typeof row.__rowIndex === "number" ? row.__rowIndex : -1;
          const value = cell.getValue();
          const text = decimalsOrString(value, decimalPlaces);

          if (column.style) {
            applyMetaStyle(el, column.style as Record<string, unknown>);
          }
          if (rowIndex >= 0) {
            const cellMeta = cellMetaByField.get(`${rowIndex}:${field}`);
            if (cellMeta) applyMetaStyle(el, cellMeta as Record<string, unknown>);
          }
          if (group.highlighted) el.classList.add("tab-col-highlighted");
          return text;
        },
      };
    };

    if (!grouped) {
      const out: ColumnDefinition[] = [];
      table.columns.forEach((group) => {
        group.columns.forEach((col) => out.push(buildLeaf(group, col)));
      });
      return out;
    }

    return table.columns.map((group, gi) => ({
      title: group.title || "",
      headerHozAlign: "center",
      frozen: group.frozen === "left" || gi === 0 ? true : undefined,
      cssClass: [
        group.cssClass,
        stripedGroups ? `col-group-${gi}` : "",
        group.highlighted ? "tab-group-highlighted" : "",
      ]
        .filter(Boolean)
        .join(" "),
      columns: group.columns.map((col) => buildLeaf(group, col)),
    }));
  }, [table.columns, grouped, transformedData, isCompact, cellMetaByField, stripedGroups]);

  useEffect(() => {
    if (!mountRef.current) return;
    instanceRef.current?.destroy();

    const options: Options = {
      data: transformedData,
      columns,
      layout: isCompact ? "fitData" : "fitColumns",
      responsiveLayout: false,
      pagination: false,
      movableColumns: false,
      rowHeight: 40,
      height: "auto",
      columnHeaderVertAlign: "middle",
      placeholder: "No data",
      rowFormatter: (row) => {
        const el = row.getElement();
        const idx = row.getPosition();
        if (rowStriping && typeof idx === "number" && idx % 2 === 1) {
          el.classList.add("bowlyzer-row-stripe");
        } else {
          el.classList.remove("bowlyzer-row-stripe");
        }
        const dataRow = row.getData() as { __rowIndex?: number };
        if (typeof dataRow.__rowIndex === "number") {
          const rowMeta = table.row_metadata?.[dataRow.__rowIndex];
          const styling = rowMeta?.styling;
          if (styling && typeof styling === "object") {
            applyMetaStyle(el, styling as Record<string, unknown>);
          }
        }
      },
    };

    const tab = new TabulatorConstructor(mountRef.current, options);
    instanceRef.current = tab;

    const runPostProcess = () => {
      const tableEl = mountRef.current?.closest(".legacyPortWrap")?.querySelector(".tabulator");
      if (tableEl) {
        tableEl.classList.add("custom-tabulator");
        applyLegacyPostProcessing(tableEl as HTMLElement, table.columns, stripedGroups);
        applyHighlighting(tableEl as HTMLElement, table.columns);
        if (!hasGroupTitles) {
          hideEmptyGroupHeaderRows(tableEl as HTMLElement);
        }
      }
    };

    tab.on("tableBuilt", () => {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => runPostProcess());
      });
    });
    tab.on("dataProcessed", () => {
      requestAnimationFrame(() => runPostProcess());
    });

    return () => {
      tab.destroy();
      instanceRef.current = null;
    };
  }, [columns, transformedData, isCompact, table.columns, table.row_metadata, rowStriping, stripedGroups, hasGroupTitles]);

  return (
    <div className={`legacyPortWrap ${scopeClass}`}>
      <div className="legacyPortMount" ref={mountRef} />
    </div>
  );
}

