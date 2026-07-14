import type { EChartsOption } from "echarts";
import type { TournamentPodiumGroup } from "../hooks/useTournament";
import { getPaletteColor } from "./color-utils";
import { compareSeasonString } from "./playerClubHistory";
import { formatTournamentAverage } from "./tournamentChartUtils";
import {
  normalizeTournamentGroupName,
  tournamentGroupAbbreviation,
} from "./tournamentGroupName";

export type TournamentOverviewSeasonPoint = {
  winner: string;
  winnerAverage: number | null;
  tournamentAverage: number | null;
};

export type TournamentOverviewAverageMode = "winner" | "field";

export type TournamentOverviewAverageGroup = {
  id: string;
  label: string;
  color: string;
  points: Record<string, TournamentOverviewSeasonPoint>;
};

export function buildTournamentOverviewAverageGroups(
  podiums: TournamentPodiumGroup[],
): TournamentOverviewAverageGroup[] {
  const grouped = new Map<string, Record<string, TournamentOverviewSeasonPoint>>();

  for (const podium of podiums) {
    const winner = podium.finishers?.find((entry) => entry.rank === 1) ?? podium.finishers?.[0];
    const winnerAverage = winner?.average ?? null;
    const tournamentAverage = podium.tournament_average ?? null;
    if (winnerAverage == null && tournamentAverage == null) continue;

    const group =
      podium.tournament_group?.trim() || normalizeTournamentGroupName(podium.tournament);
    if (!group) continue;

    const season = String(podium.season ?? "").trim();
    if (!season) continue;

    const bucket = grouped.get(group) ?? {};
    bucket[season] = {
      winner: winner?.player?.trim() ?? "—",
      winnerAverage,
      tournamentAverage,
    };
    grouped.set(group, bucket);
  }

  const entries = [...grouped.entries()]
    .map(([group, points]) => ({
      id: group,
      label: tournamentGroupAbbreviation(group) ?? group,
      points,
    }))
    .filter((entry) => Object.keys(entry.points).length > 0)
    .sort((a, b) => a.label.localeCompare(b.label, "de"));

  return entries.map((entry, index) => ({
    id: entry.id,
    label: entry.label,
    color: getPaletteColor(index % 10),
    points: entry.points,
  }));
}

function averageAxisBounds(
  groups: TournamentOverviewAverageGroup[],
  mode: TournamentOverviewAverageMode,
): { min: number; max: number } {
  const values: number[] = [];
  for (const group of groups) {
    for (const point of Object.values(group.points)) {
      const value = mode === "winner" ? point.winnerAverage : point.tournamentAverage;
      if (value != null && Number.isFinite(value)) {
        values.push(value);
      }
    }
  }
  if (values.length === 0) return { min: 150, max: 220 };
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const padding = Math.max(2, (maxValue - minValue) * 0.08);
  return {
    min: Math.floor(minValue - padding),
    max: Math.ceil(maxValue + padding),
  };
}

export function buildTournamentOverviewAverageChartOption(
  groups: TournamentOverviewAverageGroup[],
  mode: TournamentOverviewAverageMode = "winner",
): EChartsOption | null {
  if (groups.length === 0) return null;

  const seasonSet = new Set<string>();
  for (const group of groups) {
    Object.keys(group.points).forEach((season) => seasonSet.add(season));
  }
  const seasons = [...seasonSet].sort(compareSeasonString);
  if (seasons.length === 0) return null;

  const { min, max } = averageAxisBounds(groups, mode);

  const series = groups.map((group) => {
    const values = seasons.map((season) => {
      const point = group.points[season];
      if (!point) return null;
      return mode === "winner" ? point.winnerAverage : point.tournamentAverage;
    });
    return {
      name: group.label,
      type: "line" as const,
      data: values,
      smooth: false,
      connectNulls: false,
      symbol: "circle",
      symbolSize: 10,
      lineStyle: { width: 2, color: group.color },
      itemStyle: {
        color: group.color,
        borderColor: group.color,
        borderWidth: 2,
      },
    };
  });

  return {
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => {
        const items = Array.isArray(params) ? params : [params];
        const idx = (items[0] as { dataIndex?: number })?.dataIndex ?? 0;
        const season = seasons[idx];
        const entries: Array<{ average: number; line: string }> = [];
        for (const group of groups) {
          const point = group.points[season];
          if (!point) continue;
          if (mode === "winner") {
            const winnerAvg = point.winnerAverage;
            const winnerAvgLabel = formatTournamentAverage(winnerAvg);
            if (winnerAvgLabel != null && winnerAvg != null) {
              entries.push({
                average: winnerAvg,
                line: `${group.label}: ${point.winner} (Ø ${winnerAvgLabel})`,
              });
            }
          } else {
            const fieldAvg = point.tournamentAverage;
            const fieldAvgLabel = formatTournamentAverage(fieldAvg);
            if (fieldAvgLabel != null && fieldAvg != null) {
              entries.push({
                average: fieldAvg,
                line: `${group.label}: Ø ${fieldAvgLabel}`,
              });
            }
          }
        }
        entries.sort((a, b) => b.average - a.average);
        const lines = [`<strong>${season}</strong>`, ...entries.map((entry) => entry.line)];
        return lines.join("<br/>");
      },
    },
    legend: groups.length > 1 ? { bottom: 0, type: "scroll" } : undefined,
    grid: {
      left: 56,
      right: 24,
      top: 40,
      bottom: groups.length > 1 ? 56 : 32,
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
      position: "left",
      axisLine: { onZero: false },
      min,
      max,
      axisLabel: {
        fontFamily: "JetBrains Mono, monospace",
      },
      splitLine: {
        show: true,
        lineStyle: { color: "rgba(0,0,0,0.1)" },
      },
    },
    series,
  };
}
