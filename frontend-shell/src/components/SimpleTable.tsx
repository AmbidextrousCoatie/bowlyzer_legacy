import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { TableData } from "../types";
import HoverTooltip from "./HoverTooltip";
import { useHoverTooltip } from "../hooks/useHoverTooltip";
import { lookupTeamColor, resolveTeamColorForRow } from "../lib/teamColors";
import { THEME, rgbaFromHex } from "../lib/theme";

type Props = {
  table: TableData;
  cellStyle?: (value: unknown, col: string, row: Record<string, unknown>) => CSSProperties | undefined;
  cellTooltip?: (value: unknown, col: string, row: Record<string, unknown>) => string;
  teamColors?: Record<string, string>;
  useTeamColorFirstColumn?: boolean;
  limit?: number;
  paginate?: boolean;
  stickyHeader?: boolean;
  frozenColumns?: number;
  horizontalStriping?: boolean;
  verticalStripeMode?: "none" | "column" | "group";
};

export default function SimpleTable({
  table,
  cellStyle,
  cellTooltip,
  teamColors,
  useTeamColorFirstColumn = false,
  limit,
  paginate = true,
  stickyHeader = true,
  frozenColumns = 1,
  horizontalStriping = true,
  verticalStripeMode = "group",
}: Props) {
  const { tooltip, onEnter, onMove, onLeave } = useHoverTooltip();
  const [sortBy, setSortBy] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [pageSize, setPageSize] = useState(10);
  const [page, setPage] = useState(1);
  const headerRefs = useRef<(HTMLTableCellElement | null)[]>([]);
  const [stickyLeft, setStickyLeft] = useState<number[]>([]);

  const flatColumns = useMemo(
    () =>
      table.columns.flatMap((g, groupIndex) =>
        g.columns.map((c, colInGroupIndex) => ({
          ...c,
          groupTitle: g.title,
          groupIndex,
          colInGroupIndex,
          frozenGroup: g.frozen === "left",
        })),
      ),
    [table.columns],
  );
  const hasGroupHeaders = table.columns.length > 1 || table.columns.some((g) => g.title && g.title.trim().length > 0);

  const effectiveFrozenColumns = useMemo(() => {
    const byGroup = flatColumns.filter((c) => c.frozenGroup).length;
    return Math.max(frozenColumns, byGroup);
  }, [flatColumns, frozenColumns]);

  useLayoutEffect(() => {
    if (effectiveFrozenColumns <= 0) {
      setStickyLeft([]);
      return;
    }
    const offsets: number[] = [];
    let running = 0;
    for (let i = 0; i < effectiveFrozenColumns && i < flatColumns.length; i += 1) {
      offsets[i] = running;
      const width = headerRefs.current[i]?.offsetWidth ?? 140;
      running += width;
    }
    setStickyLeft(offsets);
  }, [flatColumns, effectiveFrozenColumns, rowsSignature(table.rows)]);

  const baseRows = typeof limit === "number" ? table.rows.slice(0, limit) : table.rows;

  const sortedRows = useMemo(() => {
    if (!sortBy) return baseRows;
    const rowsCopy = [...baseRows];
    rowsCopy.sort((a, b) => {
      const av = a[sortBy];
      const bv = b[sortBy];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") {
        return sortDir === "asc" ? av - bv : bv - av;
      }
      const as = String(av).toLowerCase();
      const bs = String(bv).toLowerCase();
      return sortDir === "asc" ? as.localeCompare(bs) : bs.localeCompare(as);
    });
    return rowsCopy;
  }, [baseRows, sortBy, sortDir]);

  const totalPages = paginate ? Math.max(1, Math.ceil(sortedRows.length / pageSize)) : 1;
  const safePage = Math.min(page, totalPages);
  const rows = paginate
    ? sortedRows.slice((safePage - 1) * pageSize, safePage * pageSize)
    : sortedRows;

  function toggleSort(col: string) {
    if (sortBy === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      return;
    }
    setSortBy(col);
    setSortDir("asc");
  }

  function firstColumnDotColor(row: Record<string, unknown>, firstField: string): string {
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

  function stripeStyle(rowIndex: number, colIndex: number, groupIndex: number): CSSProperties | undefined {
    const style: CSSProperties = {};
    if (horizontalStriping && rowIndex % 2 === 1) {
      style.backgroundColor = rgbaFromHex(THEME.neutral.slate900, 0.03);
    }
    if (verticalStripeMode === "column" && colIndex % 2 === 1) {
      style.backgroundColor = mergeStripe(style.backgroundColor, rgbaFromHex(THEME.brand.teal700, 0.04));
    }
    if (verticalStripeMode === "group" && groupIndex % 2 === 1) {
      style.backgroundColor = mergeStripe(style.backgroundColor, rgbaFromHex(THEME.brand.teal700, 0.06));
    }
    return Object.keys(style).length > 0 ? style : undefined;
  }

  return (
    <div className="heatmapWrap">
      <table className="dataTable">
        <thead>
          {hasGroupHeaders ? (
            <tr>
              {table.columns.map((group, gi) => (
                <th
                  key={`st-gh-${gi}`}
                  colSpan={group.columns.length}
                  className={stickyHeader ? "stickyHeader" : undefined}
                >
                  {group.title || "\u00A0"}
                </th>
              ))}
            </tr>
          ) : null}
          <tr>
            {flatColumns.map((col, idx) => (
              <th
                ref={(el) => {
                  headerRefs.current[idx] = el;
                }}
                key={`st-h-${col.field}`}
                className="sortableHeader"
                onClick={() => toggleSort(col.field)}
                title={`Sort by ${col.field}`}
                style={{
                  ...(stickyHeader ? { top: hasGroupHeaders ? 32 : 0 } : {}),
                  ...(idx < effectiveFrozenColumns
                    ? {
                        position: "sticky",
                        left: stickyLeft[idx] ?? 0,
                        zIndex: 4,
                      }
                    : {}),
                }}
              >
                {col.field}
                {sortBy === col.field ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={`st-r-${idx}`}>
              {flatColumns.map((col, cIdx) => (
                <td
                  key={`st-c-${idx}-${col.field}`}
                  className={tooltip.cellKey === `st-${idx}-${col.field}` ? "tableCellActive" : undefined}
                  style={{
                    ...stripeStyle(idx, cIdx, col.groupIndex),
                    ...(cellStyle ? cellStyle(row[col.field], col.field, row) : undefined),
                    ...(cIdx < effectiveFrozenColumns
                      ? {
                          position: "sticky",
                          left: stickyLeft[cIdx] ?? 0,
                          zIndex: 2,
                        }
                      : {}),
                  }}
                  onMouseEnter={(e) =>
                    onEnter(
                      e,
                      cellTooltip ? cellTooltip(row[col.field], col.field, row) : `${col.field}: ${String(row[col.field] ?? "")}`,
                      `st-${idx}-${col.field}`,
                    )
                  }
                  onMouseMove={onMove}
                  onMouseLeave={onLeave}
                >
                  {cIdx === 0 && useTeamColorFirstColumn ? (
                    <span className="firstColWithTeamColor">
                      <span
                        className="teamColorDot"
                        style={{ backgroundColor: firstColumnDotColor(row, flatColumns[0]?.field ?? "") }}
                        aria-hidden="true"
                      />
                      <span>{String(row[col.field] ?? "")}</span>
                    </span>
                  ) : (
                    String(row[col.field] ?? "")
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {paginate ? (
        <div className="tableControls">
          <div className="tableControlsLeft">
            <label>
              Rows per page
              <select
                value={pageSize}
                onChange={(e) => {
                  const nextSize = Number(e.target.value);
                  setPageSize(nextSize);
                  setPage(1);
                }}
              >
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
              </select>
            </label>
          </div>
          <div className="tableControlsRight">
            <button type="button" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={safePage <= 1}>
              Prev
            </button>
            <span>
              Page {safePage} / {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={safePage >= totalPages}
            >
              Next
            </button>
          </div>
        </div>
      ) : null}
      <HoverTooltip visible={tooltip.visible} x={tooltip.x} y={tooltip.y} content={tooltip.content} />
    </div>
  );
}

function rowsSignature(rows: Array<Record<string, unknown>>): string {
  return `${rows.length}:${rows.length > 0 ? Object.keys(rows[0]).join(",") : ""}`;
}

function mergeStripe(base: string | undefined, overlay: string): string {
  return base ? base : overlay;
}
