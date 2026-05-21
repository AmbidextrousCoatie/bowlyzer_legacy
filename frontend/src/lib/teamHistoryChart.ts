import type { EChartsOption } from "echarts";
import type { TeamHistory, TeamHistorySeason } from "../hooks/useTeam";
import { compareSeasonString } from "./playerClubHistory";

export const LEAGUE_AXIS_LABELS: Record<number, string> = {
  1: "1. Bundesliga",
  2: "2. Bundesliga",
  3: "Bayernliga",
  4: "Landesliga",
  5: "Bezirksoberliga",
  6: "Bezirksliga",
  7: "Kreisliga",
};

const LEAGUE_LABEL_VALUES = [5, 15, 25, 35, 45, 55, 65];
const LEAGUE_BORDER_VALUES = [10, 20, 30, 40, 50, 60, 70];

function leagueLabelForAxisValue(value: number): string {
  const level = Math.floor((value - 1) / 10) + 1;
  return LEAGUE_AXIS_LABELS[level] ?? "";
}

export function combinedPositionValue(row: TeamHistorySeason): number {
  return (row.league_level - 1) * 10 + row.final_position;
}

export type PositionSeriesInput = {
  id: string;
  label: string;
  color: string;
  history: TeamHistory;
};

export function buildPositionHistoryChartOption(
  seriesList: PositionSeriesInput[],
): EChartsOption | null {
  if (seriesList.length === 0) return null;

  const seasonSet = new Set<string>();
  for (const s of seriesList) {
    Object.keys(s.history).forEach((k) => seasonSet.add(k));
  }
  const seasons = [...seasonSet].sort(compareSeasonString);
  if (seasons.length === 0) return null;

  return {
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => {
        const items = Array.isArray(params) ? params : [params];
        const idx = (items[0] as { dataIndex?: number })?.dataIndex ?? 0;
        const season = seasons[idx];
        const lines = [`<strong>${season}</strong>`];
        for (const p of items) {
          const param = p as { seriesName?: string; data?: number | null };
          if (param.data == null || Number.isNaN(param.data)) continue;
          const series = seriesList.find((s) => s.label === param.seriesName);
          const row = series?.history[season];
          if (!row) continue;
          lines.push(
            `${param.seriesName}: ${row.final_position}. (${row.league_name})`,
          );
        }
        return lines.join("<br/>");
      },
    },
    legend: seriesList.length > 1 ? { bottom: 0, type: "scroll" } : undefined,
    grid: {
      left: 120,
      right: 24,
      top: 40,
      bottom: seriesList.length > 1 ? 56 : 32,
    },
    // boundaryGap % is supported at runtime; echarts types only allow boolean.
    xAxis: {
      type: "category",
      data: seasons,
      boundaryGap: ["20%", "20%"],
      position: "bottom",
      axisLine: { show: true, onZero: false },
      axisTick: { show: true, alignWithLabel: true },
      axisLabel: { show: true },
      splitLine: { show: false },
    } as unknown as NonNullable<EChartsOption["xAxis"]>,
    yAxis: {
      type: "value",
      inverse: true,
      position: "left",
      axisLine: { onZero: false },
      min: 0,
      max: 70,
      interval: 10,
      axisLabel: {
        customValues: LEAGUE_LABEL_VALUES,
        formatter: (value: number) => leagueLabelForAxisValue(value),
        width: 112,
        overflow: "truncate",
      },
      axisTick: {
        show: true,
        length: 6,
        customValues: LEAGUE_BORDER_VALUES,
      },
      minorTick: { show: false },
      splitLine: {
        show: true,
        lineStyle: { color: "rgba(0,0,0,0.1)" },
      },
    },
    series: seriesList.map((s) => {
      const positions = seasons.map((season) => s.history[season]?.final_position ?? null);
      const values = seasons.map((season) => {
        const row = s.history[season];
        return row ? combinedPositionValue(row) : null;
      });
      return {
        name: s.label,
        type: "line" as const,
        data: values,
        smooth: false,
        connectNulls: false,
        symbol: "circle",
        symbolSize: 28,
        lineStyle: { width: 2, color: s.color },
        itemStyle: {
          color: s.color,
          borderColor: s.color,
          borderWidth: 2,
        },
        label: {
          show: true,
          position: "inside" as const,
          color: "#fff",
          fontWeight: 600,
          fontSize: 12,
          fontFamily: "JetBrains Mono, monospace",
          formatter: (params: { dataIndex?: number }) => {
            const idx = params.dataIndex ?? 0;
            const pos = positions[idx];
            return pos != null ? String(pos) : "";
          },
        },
      };
    }),
  };
}
