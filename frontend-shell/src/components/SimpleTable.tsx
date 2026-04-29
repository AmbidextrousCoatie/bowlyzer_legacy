import type { CSSProperties } from "react";
import type { TableData } from "../types";

type Props = {
  table: TableData;
  cellStyle?: (value: unknown, col: string, row: Record<string, unknown>) => CSSProperties | undefined;
  limit?: number;
};

export default function SimpleTable({ table, cellStyle, limit }: Props) {
  const columns = table.columns.flatMap((g) => g.columns.map((c) => c.field));
  const rows = typeof limit === "number" ? table.rows.slice(0, limit) : table.rows;
  return (
    <div className="heatmapWrap">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={`st-h-${c}`}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={`st-r-${idx}`}>
              {columns.map((c) => (
                <td key={`st-c-${idx}-${c}`} style={cellStyle ? cellStyle(row[c], c, row) : undefined}>
                  {String(row[c] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
