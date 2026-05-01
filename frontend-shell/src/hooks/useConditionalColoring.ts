import { useMemo } from "react";
import type { CSSProperties } from "react";
import type { ColorMode, TableData } from "../types";
import { THEME, rgbaFromHex } from "../lib/theme";

export function useConditionalColoring(standings: TableData | null) {
  const standingsColumns = useMemo(() => {
    if (!standings) return [];
    return standings.columns.flatMap((g) => g.columns.map((c) => c.field));
  }, [standings]);

  const standingsColumnStats = useMemo(() => {
    if (!standings) return {};
    const stats: Record<string, { min: number; max: number; avg: number }> = {};
    standingsColumns.forEach((col) => {
      const values = standings.rows
        .map((r) => r[col])
        .filter((v): v is number => typeof v === "number");
      if (values.length > 1) {
        const min = Math.min(...values);
        const max = Math.max(...values);
        const avg = values.reduce((a, b) => a + b, 0) / values.length;
        stats[col] = { min, max, avg };
      }
    });
    return stats;
  }, [standings, standingsColumns]);

  function getConditionalCellStyle(value: unknown, col: string, mode: ColorMode): CSSProperties | undefined {
    if (mode === "off" || typeof value !== "number") return undefined;
    const stat = standingsColumnStats[col];
    if (!stat || stat.max === stat.min) return undefined;

    if (mode === "sequential") {
      const t = (value - stat.min) / (stat.max - stat.min);
      const bg = rgbaFromHex(THEME.brand.blue600, 0.12 + t * 0.55);
      return { backgroundColor: bg, color: t > 0.68 ? THEME.neutral.white : THEME.neutral.slate900 };
    }

    const span = Math.max(Math.abs(stat.max - stat.avg), Math.abs(stat.min - stat.avg), 1);
    const t = (value - stat.avg) / span;
    if (t >= 0) {
      const alpha = 0.1 + Math.min(t, 1) * 0.55;
      return {
        backgroundColor: rgbaFromHex(THEME.state.success, alpha),
        color: t > 0.72 ? THEME.neutral.white : THEME.state.successDark,
      };
    }
    const alpha = 0.1 + Math.min(Math.abs(t), 1) * 0.55;
    return {
      backgroundColor: rgbaFromHex(THEME.state.danger, alpha),
      color: Math.abs(t) > 0.72 ? THEME.neutral.white : THEME.state.dangerDark,
    };
  }

  return { getConditionalCellStyle };
}
