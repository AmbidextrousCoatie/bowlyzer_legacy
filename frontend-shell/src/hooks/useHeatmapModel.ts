import { useMemo } from "react";
import type { CSSProperties } from "react";
import type { HeatmapGroupingMode, HeatmapNormMode, TableData } from "../types";

export function useHeatmapModel(teamVsTeam: TableData | null, groupingMode: HeatmapGroupingMode, normMode: HeatmapNormMode) {
  const heatmapModel = useMemo(() => {
    if (!teamVsTeam) return null;
    const fields = teamVsTeam.columns.flatMap((g) => g.columns.map((c) => c.field));
    if (fields.length < 2) return null;
    const rowLabelField = fields[0];
    const valueFields = fields.slice(1);

    const columnStats = valueFields
      .map((field) => {
        const values = teamVsTeam.rows
          .map((r) => r[field])
          .filter((v): v is number => typeof v === "number");
        if (values.length === 0) return null;
        const min = Math.min(...values);
        const max = Math.max(...values);
        const avg = values.reduce((a, b) => a + b, 0) / values.length;
        const magnitude = Math.floor(Math.log10(Math.max(Math.abs(min), Math.abs(max), 1)));
        return { field, min, max, avg, magnitude };
      })
      .filter((s): s is { field: string; min: number; max: number; avg: number; magnitude: number } => s !== null);

    const groupedFields = new Map<string, string[]>();
    if (groupingMode === "single") {
      groupedFields.set("all-metrics", columnStats.map((s) => s.field));
    } else {
      columnStats.forEach((s) => {
        const lower = s.field.toLowerCase();
        if (lower.includes("point")) {
          const list = groupedFields.get("points") ?? [];
          list.push(s.field);
          groupedFields.set("points", list);
          return;
        }
        if (lower.includes("score") || lower.includes("avg") || lower.includes("average")) {
          const list = groupedFields.get("scores") ?? [];
          list.push(s.field);
          groupedFields.set("scores", list);
          return;
        }
        const key = `scale-10^${s.magnitude}`;
        const list = groupedFields.get(key) ?? [];
        list.push(s.field);
        groupedFields.set(key, list);
      });
    }

    const groups = Array.from(groupedFields.entries()).map(([name, fieldsInGroup]) => {
      const values = teamVsTeam.rows
        .flatMap((r) => fieldsInGroup.map((f) => r[f]))
        .filter((v): v is number => typeof v === "number");
      const min = values.length > 0 ? Math.min(...values) : 0;
      const max = values.length > 0 ? Math.max(...values) : 1;
      return { name, fields: fieldsInGroup, min, max };
    });

    return { rowLabelField, groups };
  }, [teamVsTeam, groupingMode]);

  function getHeatColor(value: unknown, rowValues: number[] | null, groupMin: number, groupMax: number): CSSProperties | undefined {
    if (typeof value !== "number" || !heatmapModel) return undefined;
    const min = normMode === "row" && rowValues && rowValues.length > 0 ? Math.min(...rowValues) : groupMin;
    const max = normMode === "row" && rowValues && rowValues.length > 0 ? Math.max(...rowValues) : groupMax;
    const range = max - min || 1;
    const t = (value - min) / range;
    const alpha = 0.08 + t * 0.62;
    return { backgroundColor: `rgba(14, 116, 144, ${alpha})`, color: t > 0.65 ? "#ffffff" : "#083344" };
  }

  return { heatmapModel, getHeatColor };
}
