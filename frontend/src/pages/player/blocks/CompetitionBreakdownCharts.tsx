import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import { EChart } from "../../../lib/charts/EChart";
import { getPaletteColor } from "../../../lib/color-utils";
import type { PlayerSeasonRow } from "../../../hooks/usePlayer";
import { useCompactChartLayout } from "../../../hooks/useMatchMedia";
import {
  breakdownSortedByAverage,
  buildCompetitionBreakdown,
  buildGamesSharePieSlices,
} from "../../../lib/playerCompetitionBreakdown";

type Props = {
  seasons: PlayerSeasonRow[];
  t: (key: string, fallback?: string) => string;
  formatCompetition: (name: string, options?: { isTournament?: boolean }) => string;
};

export function CompetitionBreakdownCharts({ seasons, t, formatCompetition }: Props) {
  const compactLayout = useCompactChartLayout();
  const breakdown = useMemo(() => buildCompetitionBreakdown(seasons), [seasons]);
  const byAverage = useMemo(() => breakdownSortedByAverage(breakdown), [breakdown]);
  const pieSlices = useMemo(() => buildGamesSharePieSlices(breakdown), [breakdown]);

  const labelFor = (name: string, isTournament: boolean) =>
    formatCompetition(name, { isTournament });

  const averageOption = useMemo<EChartsOption | null>(() => {
    if (byAverage.length === 0) return null;

    const names = byAverage.map((e) => labelFor(e.name, e.isTournament));
    const averages = byAverage.map((e) => Number(e.average.toFixed(2)));
    const min = Math.floor(Math.min(...averages) - 5);
    const max = Math.ceil(Math.max(...averages) + 5);

    return {
      animation: false,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (raw: unknown) => {
          const params = raw as Array<{ dataIndex?: number; value?: number }>;
          const idx = params[0]?.dataIndex ?? 0;
          const entry = byAverage[idx];
          if (!entry) return "";
          return [
            `<strong>${entry.name}</strong>`,
            `${t("ui.player.average_col", "Schnitt")}: <b>${entry.average.toFixed(2)}</b>`,
            `${t("ui.player.games", "Spiele")}: <b>${entry.games}</b>`,
            `${t("ui.player.competition_share", "Anteil")}: <b>${entry.sharePct.toFixed(1)}%</b>`,
          ].join("<br/>");
        },
      },
      grid: { left: 12, right: 24, top: 8, bottom: 8, containLabel: true },
      xAxis: {
        type: "value",
        min,
        max,
        name: t("ui.player.average_score_axis", "Durchschnitt"),
        nameLocation: "middle",
        nameGap: 28,
      },
      yAxis: {
        type: "category",
        data: names,
        inverse: true,
        axisLabel: {
          width: compactLayout ? 96 : 140,
          overflow: "truncate",
        },
      },
      series: [
        {
          name: t("ui.player.average_col", "Schnitt"),
          type: "bar",
          data: averages.map((value, idx) => ({
            value,
            itemStyle: { color: getPaletteColor(idx % 10) },
          })),
          barMaxWidth: 22,
        },
      ],
    };
  }, [byAverage, compactLayout, formatCompetition, t]);

  const shareOption = useMemo<EChartsOption | null>(() => {
    if (pieSlices.length === 0) return null;

    const sliceMeta = pieSlices.map((slice) => {
      const source = breakdown.find((e) => e.id === slice.id);
      const fullName = slice.id === "__other__" ? slice.name : (source?.name ?? slice.name);
      const isTournament = source?.isTournament ?? false;
      return {
        ...slice,
        fullName,
        chartName: slice.id === "__other__" ? slice.name : labelFor(fullName, isTournament),
      };
    });

    return {
      animation: false,
      tooltip: {
        trigger: "item",
        formatter: (raw: unknown) => {
          const p = raw as { name?: string; value?: number; percent?: number; dataIndex?: number };
          const meta = sliceMeta[p.dataIndex ?? 0];
          const heading = meta?.fullName ?? p.name ?? "";
          return [
            `<strong>${heading}</strong>`,
            `${t("ui.player.games", "Spiele")}: <b>${p.value ?? 0}</b>`,
            `${t("ui.player.competition_share", "Anteil")}: <b>${(p.percent ?? 0).toFixed(1)}%</b>`,
          ].join("<br/>");
        },
      },
      legend: compactLayout
        ? {
            type: "scroll",
            orient: "horizontal",
            bottom: 0,
            left: "center",
            width: "96%",
            itemWidth: 12,
            itemGap: 8,
            textStyle: { fontSize: 10 },
          }
        : {
            type: "scroll",
            orient: "vertical",
            right: 0,
            top: "middle",
            textStyle: { fontSize: 11 },
          },
      series: [
        {
          name: t("ui.player.games_share_title", "Spieleanteil"),
          type: "pie",
          radius: compactLayout ? ["34%", "50%"] : ["42%", "68%"],
          center: compactLayout ? ["50%", "42%"] : ["38%", "50%"],
          avoidLabelOverlap: true,
          label: { show: false },
          emphasis: {
            label: { show: true, fontSize: 12, fontWeight: "bold" },
          },
          data: sliceMeta.map((slice, idx) => ({
            name: slice.chartName,
            value: slice.games,
            itemStyle: {
              color: slice.id === "__other__" ? "#71717a" : getPaletteColor(idx % 10),
            },
          })),
        },
      ],
    };
  }, [breakdown, compactLayout, formatCompetition, pieSlices, t]);

  if (!averageOption && !shareOption) return null;

  const chartHeight = Math.max(280, byAverage.length * 30 + 48);
  const shareHeight = compactLayout ? Math.max(340, chartHeight + 72) : Math.max(280, chartHeight);

  return (
    <section className="rounded-sm border border-border bg-surface">
      <header className="border-b border-border px-4 py-3 lg:px-5">
        <p className="text-label uppercase text-muted mb-1">
          {t("ui.player.competition_breakdown_eyebrow", "Wettbewerbe")}
        </p>
        <h2 className="text-h3">
          {t("ui.player.competition_breakdown_title", "Wettbewerbsübersicht")}
        </h2>
        <p className="text-small text-muted mt-1">
          {t(
            "ui.player.competition_breakdown_hint",
            "Schnitt und Spielanteil je Wettbewerb — Ligen und Turniere zusammen.",
          )}
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 p-4 lg:grid-cols-2 lg:p-5">
        <div className="min-w-0">
          <h3 className="text-body font-semibold text-foreground mb-2">
            {t("ui.player.competition_avg_chart", "Schnitt je Wettbewerb")}
          </h3>
          {averageOption ? (
            <EChart option={averageOption} height={chartHeight} />
          ) : (
            <EmptyChart t={t} />
          )}
        </div>
        <div className="min-w-0">
          <h3 className="text-body font-semibold text-foreground mb-2">
            {t("ui.player.games_share_title", "Spieleanteil")}
          </h3>
          {shareOption ? (
            <EChart option={shareOption} height={shareHeight} />
          ) : (
            <EmptyChart t={t} />
          )}
        </div>
      </div>
    </section>
  );
}

function EmptyChart({ t }: { t: (key: string, fallback?: string) => string }) {
  return (
    <div className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
      {t("ui.player.no_competition_data", "Keine Wettbewerbsdaten vorhanden.")}
    </div>
  );
}
