import { flattenColumnMetadata } from "../datatable/flatten";
import type { RowMetaEntry, TableData } from "../datatable/types";

export type LeaderboardNetSortMode = "average" | "total";

function toNumber(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** Pandas ``rank(method='min', ascending=False)`` on one array. */
function minRankDescending(values: number[]): number[] {
  const order = values
    .map((value, index) => ({ value, index }))
    .sort((left, right) => right.value - left.value || left.index - right.index);
  const ranks = new Array<number>(values.length).fill(0);
  let rank = 1;
  for (let i = 0; i < order.length; i += 1) {
    if (i > 0 && order[i].value < order[i - 1].value) {
      rank = i + 1;
    }
    ranks[order[i].index] = rank;
  }
  return ranks;
}

function rowAsRecord(row: unknown, fields: string[]): Record<string, unknown> {
  if (Array.isArray(row)) {
    const out: Record<string, unknown> = {};
    fields.forEach((field, index) => {
      if (index < row.length) out[field] = row[index];
    });
    return out;
  }
  return { ...(row as Record<string, unknown>) };
}

function recordAsRow(record: Record<string, unknown>, fields: string[]): unknown[] {
  return fields.map((field) => record[field]);
}

function inferCutPosition(data: TableData): number | null {
  const cellMetadata = data.cell_metadata ?? {};
  for (const [key, style] of Object.entries(cellMetadata)) {
    const [, colStr] = key.split(":");
    if (colStr !== "0") continue;
    const bg = String(style.backgroundColor ?? "").toLowerCase();
    if (bg !== "#ffe8a1") continue;
    const rowIdx = Number.parseInt(key.split(":")[0] ?? "", 10);
    if (Number.isNaN(rowIdx) || rowIdx < 0 || rowIdx >= data.data.length) continue;
    const row = data.data[rowIdx];
    if (Array.isArray(row)) return toNumber(row[0]);
    return toNumber((row as Record<string, unknown>).rank);
  }
  return null;
}

/** Mirror ``TournamentService._cut_row_style_for_rank`` for rank-column cell metadata. */
function cutCellStyleForRank(
  rank: number,
  cutPos: number | null,
): Record<string, string | number> | undefined {
  if (cutPos == null || rank <= 0) return undefined;
  if (rank === 1) return { backgroundColor: "#cfead6", fontWeight: "700" };
  if (rank < cutPos) return { backgroundColor: "#e6f4ea" };
  if (rank === cutPos) return { backgroundColor: "#ffe8a1", fontWeight: "700" };
  return undefined;
}

export function leaderboardSupportsNetSort(data: TableData): boolean {
  const mode = data.metadata?.leaderboard_mode;
  if (mode !== "scratch_net_handicap") return false;
  if (data.metadata?.initial_sort) return false;
  if (data.metadata?.kind === "ko_placements") return false;
  const fields = flattenColumnMetadata(data.columns).map((info) => info.field);
  return fields.includes("total_net") && fields.includes("avg_net");
}

export function resortLeaderboardByNetMetric(
  data: TableData,
  mode: LeaderboardNetSortMode,
): TableData {
  if (!leaderboardSupportsNetSort(data)) return data;

  const flat = flattenColumnMetadata(data.columns);
  const fields = flat.map((info) => info.field);
  const rankField = "rank";
  const sortField = mode === "average" ? "avg_net" : "total_net";
  const playerField = fields.includes("player") ? "player" : fields[1] ?? "";

  const parsed = data.data.map((row, oldIndex) => ({
    oldIndex,
    record: rowAsRecord(row, fields),
  }));

  parsed.sort((left, right) => {
    const sortDelta =
      toNumber(right.record[sortField]) - toNumber(left.record[sortField]);
    if (sortDelta !== 0) return sortDelta;
    const nameLeft = String(left.record[playerField] ?? "");
    const nameRight = String(right.record[playerField] ?? "");
    return nameLeft.localeCompare(nameRight, "de");
  });

  const sortValues = parsed.map((entry) => toNumber(entry.record[sortField]));
  const ranks = minRankDescending(sortValues);

  const cutPos = inferCutPosition(data);
  const newData: TableData["data"] = [];
  const newRowMetadata: RowMetaEntry[] = [];
  const newCellMetadata: NonNullable<TableData["cell_metadata"]> = {};
  const oldRowMetadata = data.row_metadata ?? [];

  parsed.forEach((entry, newIndex) => {
    const rank = ranks[newIndex];
    const record = { ...entry.record, [rankField]: rank };
    const isArray = Array.isArray(data.data[entry.oldIndex]);
    newData.push(isArray ? recordAsRow(record, fields) : record);

    const oldMeta = oldRowMetadata[entry.oldIndex];
    const nextMeta =
      oldMeta && typeof oldMeta === "object"
        ? { ...oldMeta, cut_shade_rank: rank }
        : { cut_shade_rank: rank };
    newRowMetadata.push(nextMeta);

    const rankStyle = cutCellStyleForRank(rank, cutPos);
    if (rankStyle) {
      newCellMetadata[`${newIndex}:0`] = rankStyle;
    }
  });

  return {
    ...data,
    data: newData,
    row_metadata: newRowMetadata,
    cell_metadata: Object.keys(newCellMetadata).length > 0 ? newCellMetadata : undefined,
    default_sort: { field: sortField, dir: "desc" },
  };
}
