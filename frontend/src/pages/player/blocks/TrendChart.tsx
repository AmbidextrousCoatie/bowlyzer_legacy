import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import { EChart } from "../../../lib/charts/EChart";
import type { PlayerLifetimeStats, PlayerSeasonRow } from "../../../hooks/usePlayer";

type Props = {
  seasons: PlayerSeasonRow[];
  lifetime: PlayerLifetimeStats | null | undefined;
  t: (key: string, fallback?: string) => string;
};

export function TrendChart({ seasons, lifetime, t }: Props) {
  const seasonTotals = useMemo(
    () => (seasons ?? []).filter((row) => (row.row_type ?? "season_total") === "season_total"),
    [seasons],
  );

  const option = useMemo<EChartsOption | null>(() => {
    if (seasonTotals.length === 0) return null;
    const lifetimeAvg = lifetime?.average_score ?? null;

    const labels = seasonTotals.map((s, i) => String(s.season ?? `Season ${i + 1}`));
    const seasonAverages = seasonTotals.map((s) => s.average ?? 0);
    const games = seasonTotals.map((s) => s.games ?? 0);
    const lifetimeLine = lifetimeAvg != null ? seasonTotals.map(() => lifetimeAvg) : null;

    const allValues = [...seasonAverages, ...(lifetimeLine ?? [])].filter((v) =>
      Number.isFinite(v),
    );
    const min = allValues.length ? Math.floor(Math.min(...allValues) - 5) : 0;
    const max = allValues.length ? Math.ceil(Math.max(...allValues) + 5) : 250;

    const seriesAverage = {
      name: t("ui.player.season_average_series", "Saisonschnitt"),
      type: "line" as const,
      data: seasonAverages,
      smooth: false,
      symbol: "circle",
      symbolSize: (_v: unknown, params: { dataIndex: number }) => {
        const g = games[params.dataIndex] ?? 0;
        return Math.max(8, Math.min(30, g / 5));
      },
      lineStyle: { width: 2, color: "#2563eb" },
      itemStyle: { color: "#2563eb" },
      z: 3,
    };

    const seriesLifetime = lifetimeLine
      ? {
          name: t("ui.player.all_time_average_series", "Karriere-Schnitt"),
          type: "line" as const,
          data: lifetimeLine,
          smooth: false,
          showSymbol: false,
          lineStyle: { width: 1.5, type: "dashed" as const, color: "#71717a" },
          itemStyle: { color: "#71717a" },
          z: 1,
        }
      : null;

    return {
      animation: false,
      tooltip: {
        trigger: "axis",
        formatter: (raw: unknown) => {
          const params = raw as Array<{
            seriesName: string;
            value: number;
            dataIndex: number;
            marker: string;
          }>;
          if (!Array.isArray(params) || params.length === 0) return "";
          const idx = params[0].dataIndex;
          const lines = params.map((p) => {
            const valueStr = Number.isFinite(p.value) ? p.value.toFixed(1) : "—";
            return `${p.marker}${p.seriesName}: <b>${valueStr}</b>`;
          });
          const games_ = games[idx] ?? 0;
          lines.push(`${t("ui.player.games", "Spiele")}: <b>${games_}</b>`);
          return [labels[idx], ...lines].join("<br/>");
        },
      },
      legend: { show: true, top: 0 },
      grid: { left: 50, right: 20, top: 30, bottom: 40, containLabel: true },
      xAxis: {
        type: "category",
        data: labels,
        name: t("ui.player.season", "Saison"),
        nameLocation: "middle",
        nameGap: 28,
      },
      yAxis: {
        type: "value",
        name: t("ui.player.average_score_axis", "Durchschnitt"),
        min,
        max,
      },
      series: seriesLifetime ? [seriesAverage, seriesLifetime] : [seriesAverage],
    };
  }, [seasonTotals, lifetime, t]);

  return (
    <section>
      <div className="mb-4">
        <p className="text-label uppercase text-muted mb-1.5">
          {t("ui.player.performance_trend", "Leistungsverlauf")}
        </p>
        <h2 className="text-h2">{t("ui.player.performance_trend", "Leistungsverlauf")}</h2>
      </div>
      {option ? (
        <div className="rounded-sm border border-border bg-surface p-3">
          <EChart option={option} height={320} />
        </div>
      ) : (
        <div className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
          {t("ui.player.no_season_data", "Keine Saisondaten vorhanden.")}
        </div>
      )}
    </section>
  );
}
