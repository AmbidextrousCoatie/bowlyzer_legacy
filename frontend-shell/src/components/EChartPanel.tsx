import { useEffect, useMemo, useRef } from "react";
import * as echarts from "echarts";
import type { ECharts, EChartsOption } from "echarts";
import type { ChartData } from "../types";
import { lookupTeamColor } from "../lib/teamColors";
import { SERIES_COLORS } from "../lib/theme";
type Props = {
  title: string;
  chart: ChartData;
  teamColors?: Record<string, string>;
  rawPayload?: unknown;
};

export default function EChartPanel({ title, chart, teamColors, rawPayload }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ECharts | null>(null);

  const valueRange = useMemo(() => {
    const values = chart.series.flatMap((s) => s.data).filter((v): v is number => typeof v === "number");
    if (values.length === 0) return null;
    return { min: Math.min(...values), max: Math.max(...values) };
  }, [chart]);

  const options = useMemo<EChartsOption>(
    () => ({
      animation: false,
      color: [...SERIES_COLORS],
      tooltip: {
        trigger: "axis",
      },
      legend: {
        top: 0,
      },
      grid: {
        top: 36,
        right: 20,
        bottom: 32,
        left: 44,
      },
      xAxis: {
        type: "category",
        data: chart.xAxis.categories.map((v) => String(v)),
      },
      yAxis: {
        type: "value",
      },
      series: chart.series.map((series) => {
        const tc = teamColors ? lookupTeamColor(teamColors, series.name) : undefined;
        return {
          name: series.name,
          type: "line",
          smooth: false,
          showSymbol: true,
          data: series.data,
          lineStyle: tc ? { color: tc } : undefined,
          itemStyle: tc ? { color: tc } : undefined,
        };
      }),
    }),
    [chart, teamColors],
  );

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;

    const instance = echarts.init(node, undefined, { renderer: "canvas" });
    chartRef.current = instance;
    instance.setOption(options, true);

    const onResize = () => instance.resize();
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      instance.dispose();
      chartRef.current = null;
    };
  }, [options]);

  return (
    <>
      <h2>{title}</h2>
      <div ref={containerRef} className="echartPanel" role="img" aria-label={`${title} line chart`} />
      {valueRange ? (
        <p className="axisHint">
          y range: {valueRange.min.toFixed(2)} - {valueRange.max.toFixed(2)}
        </p>
      ) : null}
      {rawPayload !== undefined ? (
        <details>
          <summary>Raw chart payload</summary>
          <pre>{JSON.stringify(rawPayload, null, 2)}</pre>
        </details>
      ) : null}
    </>
  );
}
