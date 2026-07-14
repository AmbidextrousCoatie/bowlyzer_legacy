import type { EChartsOption } from "echarts";
import type { TournamentPlayerResultRow } from "../hooks/useTournament";
import { getPaletteColor } from "./color-utils";
import { compareSeasonString } from "./playerClubHistory";
import {
  assignTournamentGroupColors,
  formatTournamentAverage,
  sortTournamentGroupNames,
} from "./tournamentChartUtils";
import {
  normalizeTournamentGroupName,
  tournamentGroupAbbreviation,
} from "./tournamentGroupName";

export type TournamentSeasonPoint = {
  position: number;
  average: number | null;
};

export type TournamentPositionSeries = {
  id: string;
  label: string;
  color: string;
  points: Record<string, TournamentSeasonPoint>;
};

export function buildTournamentPositionSeries(
  rows: TournamentPlayerResultRow[],
): TournamentPositionSeries[] {
  const grouped = new Map<string, Record<string, TournamentSeasonPoint>>();

  for (const row of rows) {
    const position = row.position;
    if (position == null || !Number.isFinite(position) || position <= 0) continue;

    const group =
      row.tournament_group?.trim() || normalizeTournamentGroupName(row.tournament);
    if (!group) continue;

    const bucket = grouped.get(group) ?? {};
    const season = String(row.season ?? "").trim();
    if (!season) continue;

    const existing = bucket[season];
    if (existing == null || position < existing.position) {
      bucket[season] = {
        position,
        average: row.average ?? null,
      };
    }
    grouped.set(group, bucket);
  }

  const groupNames = sortTournamentGroupNames([...grouped.keys()]);
  const colorByGroup = assignTournamentGroupColors(groupNames);

  return groupNames
    .map((group) => {
      const points = grouped.get(group) ?? {};
      if (Object.keys(points).length === 0) return null;
      return {
        id: group,
        label: tournamentGroupAbbreviation(group) ?? group,
        color: colorByGroup.get(group) ?? getPaletteColor(0),
        points,
      };
    })
    .filter((series): series is TournamentPositionSeries => series != null);
}

function rankAxisMax(maxPosition: number): number {
  if (maxPosition <= 10) return 10;
  if (maxPosition <= 20) return 20;
  if (maxPosition <= 50) return Math.ceil(maxPosition / 10) * 10;
  return Math.ceil(maxPosition / 20) * 20;
}

export function buildTournamentPositionHistoryChartOption(
  seriesList: TournamentPositionSeries[],
): EChartsOption | null {
  if (seriesList.length === 0) return null;

  const seasonSet = new Set<string>();
  let maxPosition = 1;
  for (const series of seriesList) {
    Object.entries(series.points).forEach(([season, point]) => {
      seasonSet.add(season);
      if (point.position > maxPosition) maxPosition = point.position;
    });
  }

  const seasons = [...seasonSet].sort(compareSeasonString);
  if (seasons.length === 0) return null;

  const yMax = rankAxisMax(maxPosition);

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
          const series = seriesList.find((entry) => entry.label === param.seriesName);
          const point = series?.points[season];
          const averageLabel = formatTournamentAverage(point?.average);
          const detail =
            averageLabel != null
              ? `${param.data}. (Ø ${averageLabel})`
              : `${param.data}.`;
          lines.push(`${param.seriesName}: ${detail}`);
        }
        return lines.join("<br/>");
      },
    },
    legend: seriesList.length > 1 ? { bottom: 0, type: "scroll" } : undefined,
    grid: {
      left: 56,
      right: 24,
      top: 40,
      bottom: seriesList.length > 1 ? 56 : 32,
    },
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
      min: 1,
      max: yMax,
      axisLabel: {
        fontFamily: "JetBrains Mono, monospace",
      },
      splitLine: {
        show: true,
        lineStyle: { color: "rgba(0,0,0,0.1)" },
      },
    },
    series: seriesList.map((series) => {
      const positions = seasons.map((season) => series.points[season]?.position ?? null);
      return {
        name: series.label,
        type: "line" as const,
        data: positions,
        smooth: false,
        connectNulls: false,
        symbol: "circle",
        symbolSize: 28,
        lineStyle: { width: 2, color: series.color },
        itemStyle: {
          color: series.color,
          borderColor: series.color,
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
