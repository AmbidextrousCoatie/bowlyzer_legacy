import type { EChartsOption } from "echarts";
import { getTeamColor, updateTeamColorMap } from "../color-utils";

export type SeriesData = Record<string, number[]>;

/**
 * Multi-series line chart. Used for "Position in Season Progress" (with
 * inverted Y-axis) and "Points in Season Progress".
 */
export function lineChartOption(
  data: SeriesData,
  order: string[] | undefined,
  labels: string[],
  opts: {
    invertYAxis?: boolean;
    yAxisRange?: "auto" | "exact" | null;
  } = {},
): EChartsOption {
  const { invertYAxis = false, yAxisRange = null } = opts;
  const teamOrder = order ?? Object.keys(data);
  updateTeamColorMap(teamOrder);

  let yMin: number | undefined;
  let yMax: number | undefined;
  if (yAxisRange === "auto" || yAxisRange === "exact") {
    const all = teamOrder.flatMap((team) => data[team] ?? []);
    if (all.length > 0) {
      const minVal = Math.min(...all);
      const maxVal = Math.max(...all);
      if (yAxisRange === "auto") {
        yMin = Math.max(minVal - 10, 0);
        yMax = maxVal + 10;
      } else {
        yMin = minVal;
        yMax = maxVal;
      }
    }
  }

  const series = teamOrder.map((team) => ({
    name: team,
    type: "line" as const,
    data: data[team] ?? [],
    lineStyle: { color: getTeamColor(team), width: 2 },
    itemStyle: { color: getTeamColor(team) },
    smooth: false,
  }));

  return {
    tooltip: {
      trigger: "axis",
      order: invertYAxis ? "valueAsc" : "valueDesc",
    },
    legend: { show: false },
    grid: {
      top: "10%",
      right: "5%",
      bottom: "10%",
      left: "5%",
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: labels,
      axisLine: { show: false },
      splitLine: { show: true },
    },
    yAxis: {
      type: "value",
      min: yMin,
      max: yMax,
      inverse: invertYAxis,
      axisLine: { show: true },
      axisTick: { show: true },
      splitLine: { show: true },
    },
    series,
    animation: false,
  };
}

/**
 * Scatter chart with one single-axis row per team. Used for "Points per Match
 * Day": each team gets its own horizontal axis stacked vertically, with
 * circles whose size encodes the value. n/a values are hidden by default.
 */
export function scatterMultiAxisOption(
  data: SeriesData,
  order: string[] | undefined,
  labels: string[],
  opts: {
    tooltipValueLabel?: string;
    minValue?: number | null;
    maxValue?: number | null;
    minCircleSize?: number;
    maxCircleSize?: number;
    hideNaValues?: boolean;
  } = {},
): EChartsOption {
  const {
    tooltipValueLabel = "Punkte",
    minValue = null,
    maxValue = null,
    minCircleSize = 7,
    maxCircleSize = 45,
    hideNaValues = true,
  } = opts;

  const teams = order ?? Object.keys(data);
  updateTeamColorMap(teams);

  // Compute global value bounds if not given
  let valueMin = minValue;
  let valueMax = maxValue;
  if (valueMin === null || valueMax === null) {
    const all: number[] = [];
    teams.forEach((team) => {
      (data[team] ?? []).forEach((v) => {
        if (typeof v === "number" && Number.isFinite(v)) all.push(v);
      });
    });
    if (all.length > 0) {
      if (valueMin === null) valueMin = Math.min(...all);
      if (valueMax === null) valueMax = Math.max(...all);
    } else {
      valueMin = 0;
      valueMax = 100;
    }
  }
  const valueRange = valueMax - valueMin;
  const sizeRange = maxCircleSize - minCircleSize;

  function normalize(value: number): number {
    if (valueRange === 0) return (minCircleSize + maxCircleSize) / 2;
    const clamped = Math.max(valueMin!, Math.min(valueMax!, value));
    const t = (clamped - valueMin!) / valueRange;
    return minCircleSize + t * sizeRange;
  }

  const singleAxis: NonNullable<EChartsOption["singleAxis"]> = [];
  const series: NonNullable<EChartsOption["series"]> = [];

  teams.forEach((team, idx) => {
    const isLast = idx === teams.length - 1;
    singleAxis.push({
      left: 40,
      right: 40,
      type: "category",
      boundaryGap: false,
      data: labels,
      top: `${(idx * 90) / teams.length}%`,
      height: `${90 / teams.length}%`,
      axisLabel: { show: isLast, interval: 0 },
      axisTick: { show: false },
      axisLine: {
        show: isLast,
        lineStyle: { color: isLast ? "#333" : "transparent" },
      },
      splitLine: {
        show: true,
        lineStyle: { type: "dashed", opacity: 0.3, color: "#222" },
      },
    });

    const seriesData = (data[team] ?? [])
      .map((value, index) => {
        if (hideNaValues && (value === null || value === undefined || Number.isNaN(value))) {
          return null;
        }
        const size = normalize(value);
        return [index, value, size];
      })
      .filter((d): d is [number, number, number] => d !== null);

    series.push({
      name: team,
      singleAxisIndex: idx,
      coordinateSystem: "singleAxis",
      type: "scatter",
      data: seriesData,
      symbolSize: (d: number[]) => d[2] || minCircleSize,
      itemStyle: { color: getTeamColor(team) },
    });
  });

  return {
    tooltip: {
      position: "top",
      formatter: (params: unknown) => {
        const p = params as {
          data: number[];
          seriesIndex: number;
        };
        const value = p.data[1];
        const week = labels[p.data[0]] ?? "";
        const team = teams[p.seriesIndex] ?? "";
        if (value === null || value === undefined || Number.isNaN(value)) {
          return `${team}<br/>${week}<br/>N/A`;
        }
        const isPercent =
          tooltipValueLabel.includes("%") || tooltipValueLabel.toLowerCase().includes("win");
        const formatted = isPercent
          ? value.toFixed(1)
          : value % 1 === 0
            ? value.toFixed(0)
            : value.toFixed(1);
        return `${team}<br/>${week}<br/>${tooltipValueLabel}: ${formatted}${isPercent ? "%" : ""}`;
      },
    },
    singleAxis,
    series,
    animation: false,
  };
}

/**
 * League-wide trend chart where the selected team is highlighted and every
 * other team is muted gray. Used inside team-performance to show where the
 * selected team sits in the league context.
 */
export function mutedTrendOption(
  seriesData: SeriesData,
  selectedTeam: string,
  opts: {
    invertY?: boolean;
    yAxisName?: string;
    weekLabel?: string;
  } = {},
): EChartsOption {
  const { invertY = false, yAxisName = "", weekLabel = "Spieltag" } = opts;
  const teamNames = Object.keys(seriesData);
  const labels = buildWeekLabels(seriesData, weekLabel);
  const selectedNorm = selectedTeam.trim().toLowerCase();
  updateTeamColorMap(teamNames.map((n) => n.trim()));

  const selectedColor = getTeamColor(selectedTeam.trim());
  const muted = "rgba(120, 120, 120, 0.45)";

  const series = teamNames.map((team) => {
    const isSelected = team.trim().toLowerCase() === selectedNorm;
    const vals = (seriesData[team] ?? []).map((v) =>
      v === null || v === undefined ? null : Number(v),
    );
    return {
      name: team,
      type: "line" as const,
      data: vals,
      smooth: false,
      showSymbol: false,
      lineStyle: {
        width: isSelected ? 3 : 1.5,
        color: isSelected ? selectedColor : muted,
      },
      itemStyle: { color: isSelected ? selectedColor : muted },
      z: isSelected ? 3 : 1,
    };
  });

  return {
    animation: false,
    tooltip: { trigger: "axis" },
    grid: { top: 20, left: 45, right: 20, bottom: 40 },
    xAxis: {
      type: "category",
      data: labels,
      name: weekLabel,
      nameLocation: "middle",
      nameGap: 28,
    },
    yAxis: {
      type: "value",
      name: yAxisName,
      inverse: invertY,
      min: invertY ? 1 : undefined,
    },
    series,
  };
}

/**
 * Build week labels ("Spieltag 1" … "Spieltag N") sized to the longest team
 * series in the payload.
 */
export function buildWeekLabels(data: SeriesData, weekLabel: string): string[] {
  const lengths = Object.values(data)
    .filter(Array.isArray)
    .map((arr) => arr.length);
  const n = lengths.length > 0 ? Math.max(...lengths) : 0;
  return Array.from({ length: n }, (_, i) => `${weekLabel} ${i + 1}`);
}
