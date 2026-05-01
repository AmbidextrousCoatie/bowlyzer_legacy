import { useMemo } from "react";
import type { ChartData } from "../types";
import { SERIES_COLORS } from "../lib/theme";

export const CHART_WIDTH = 900;
export const CHART_HEIGHT = 280;

export function useLineChartGeometry(pointsChart: ChartData | null) {
  const chartGeometry = useMemo(() => {
    if (!pointsChart || pointsChart.series.length === 0) return null;
    const values = pointsChart.series.flatMap((s) => s.data).filter((v): v is number => typeof v === "number");
    if (values.length === 0) return null;

    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const xCount = Math.max(pointsChart.xAxis.categories.length - 1, 1);

    const seriesPaths = pointsChart.series.map((series, idx) => {
      const points = series.data
        .map((val, i) => {
          if (val === null) return null;
          const x = (i / xCount) * CHART_WIDTH;
          const y = CHART_HEIGHT - ((val - min) / range) * CHART_HEIGHT;
          return `${x},${y}`;
        })
        .filter((p): p is string => p !== null);
      return {
        name: series.name,
        color: SERIES_COLORS[idx % SERIES_COLORS.length],
        d: points.join(" "),
      };
    });

    return { min, max, seriesPaths };
  }, [pointsChart]);

  return { chartGeometry, chartWidth: CHART_WIDTH, chartHeight: CHART_HEIGHT };
}
