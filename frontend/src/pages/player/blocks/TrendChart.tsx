import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import { EChart } from "../../../lib/charts/EChart";
import { TEAM_COLOR_PALETTES } from "../../../lib/color-utils";
import type { PlayerLifetimeStats, PlayerSeasonRow } from "../../../hooks/usePlayer";
import { buildCumulativeSeasonAverages } from "../../../lib/playerHighlights";
import { compareSeasonString } from "../../../lib/playerClubHistory";

type Props = {
  seasons: PlayerSeasonRow[];
  lifetime: PlayerLifetimeStats | null | undefined;
  t: (key: string, fallback?: string) => string;
};

const SEASON_BAR_COLOR = TEAM_COLOR_PALETTES.rainbowPastel[0];
const CUMULATIVE_LINE_COLOR = TEAM_COLOR_PALETTES.rainbowPastel[8];

export function TrendChart({ seasons, lifetime: _lifetime, t }: Props) {
  const seasonTotals = useMemo(() => {
    const totals = (seasons ?? []).filter(
      (row) => (row.row_type ?? "season_total") === "season_total",
    );
    return [...totals].sort((a, b) =>
      compareSeasonString(String(a.season ?? ""), String(b.season ?? "")),
    );
  }, [seasons]);

  const option = useMemo<EChartsOption | null>(() => {
    if (seasonTotals.length === 0) return null;

    const labels = seasonTotals.map((s, i) => String(s.season ?? `Season ${i + 1}`));
    const seasonAverages = seasonTotals.map((s) => s.average ?? 0);
    const games = seasonTotals.map((s) => s.games ?? 0);
    const cumulative = buildCumulativeSeasonAverages(seasonTotals).map((row) => row.average);

    const allValues = [...seasonAverages, ...cumulative].filter((v) => Number.isFinite(v));
    const min = allValues.length ? Math.floor(Math.min(...allValues) - 5) : 0;
    const max = allValues.length ? Math.ceil(Math.max(...allValues) + 5) : 250;

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
            const valueStr = Number.isFinite(p.value) ? p.value.toFixed(2) : "—";
            return `${p.marker}${p.seriesName}: <b>${valueStr}</b>`;
          });
          const games_ = games[idx] ?? 0;
          lines.push(`${t("ui.player.games", "Spiele")}: <b>${games_}</b>`);
          return [labels[idx], ...lines].join("<br/>");
        },
      },
      legend: { show: true, top: 0 },
      grid: { left: 50, right: 20, top: 36, bottom: 40, containLabel: true },
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
      series: [
        {
          name: t("ui.player.season_average_series", "Saisonschnitt"),
          type: "bar",
          data: seasonAverages,
          barMaxWidth: 48,
          itemStyle: { color: SEASON_BAR_COLOR },
          z: 2,
        },
        {
          name: t("ui.player.cumulative_average_series", "Kumulierter Schnitt"),
          type: "line",
          data: cumulative,
          smooth: false,
          symbol: "circle",
          symbolSize: 8,
          lineStyle: { width: 2.5, color: CUMULATIVE_LINE_COLOR },
          itemStyle: { color: CUMULATIVE_LINE_COLOR },
          z: 3,
        },
      ],
    };
  }, [seasonTotals, t]);

  return (
    <section>
      <div className="mb-4">
        <p className="text-label uppercase text-muted mb-1.5">
          {t("ui.player.performance_trend", "Leistungsverlauf")}
        </p>
        <h2 className="text-h2">{t("ui.player.performance_trend", "Leistungstrend")}</h2>
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
