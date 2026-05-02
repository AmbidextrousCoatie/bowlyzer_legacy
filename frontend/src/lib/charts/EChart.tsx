import * as echarts from "echarts";
import type { EChartsOption } from "echarts";
import { useEffect, useRef } from "react";

type EChartProps = {
  option: EChartsOption;
  height?: number | string;
  className?: string;
};

/**
 * Thin React wrapper around `echarts.init`. Mounts a canvas, mirrors the
 * given `option` via `setOption(..., true)`, observes container resizes, and
 * disposes the instance on unmount. Caller owns memoization of `option`.
 */
export function EChart({ option, height = 300, className }: EChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  // Init / dispose
  useEffect(() => {
    if (!containerRef.current) return;
    chartRef.current = echarts.init(containerRef.current, null, {
      renderer: "canvas",
      devicePixelRatio: window.devicePixelRatio,
    });
    return () => {
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  // Push option whenever it changes
  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.setOption(option, true);
    }
  }, [option]);

  // Resize on container changes
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver(() => chartRef.current?.resize());
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  return <div ref={containerRef} className={className} style={{ height, width: "100%" }} />;
}
