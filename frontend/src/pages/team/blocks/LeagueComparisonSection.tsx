import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import { EChart } from "../../../lib/charts/EChart";
import type { LeagueComparison } from "../../../hooks/useTeam";

type Props = {
  data: LeagueComparison;
  t: (key: string, fallback?: string) => string;
};

export function LeagueComparisonSection({ data, t }: Props) {
  const seasons = useMemo(() => Object.keys(data).sort(), [data]);

  const chartOption = useMemo<EChartsOption | null>(() => {
    if (seasons.length === 0) return null;
    const teamScores = seasons.map((s) => data[s].team_performance?.team_average_score ?? 0);
    const leagueScores = seasons.map((s) => data[s].league_averages?.average_score ?? 0);
    const allScores = [...teamScores, ...leagueScores].filter((v) => Number.isFinite(v));
    const dataMin = allScores.length ? Math.min(...allScores) : 0;
    const dataMax = allScores.length ? Math.max(...allScores) : 0;
    const yMin = Math.floor(dataMin) - 5;
    const yMax = Math.ceil(dataMax) + 5;

    return {
      tooltip: { trigger: "axis" },
      legend: {
        data: [
          t("ui.league_comparison.team_avg", "Mannschaft"),
          t("ui.league_comparison.league_avg", "Liga-Schnitt"),
        ],
        bottom: 0,
      },
      grid: { left: 48, right: 24, top: 24, bottom: 48 },
      xAxis: { type: "category", data: seasons },
      yAxis: {
        type: "value",
        name: t("average", "Schnitt"),
        min: yMin,
        max: yMax,
      },
      series: [
        {
          name: t("ui.league_comparison.team_avg", "Mannschaft"),
          type: "line",
          data: teamScores,
          areaStyle: { opacity: 0.15, color: "#2563eb" },
          lineStyle: { color: "#2563eb" },
          itemStyle: { color: "#2563eb" },
        },
        {
          name: t("ui.league_comparison.league_avg", "Liga-Schnitt"),
          type: "line",
          data: leagueScores,
          lineStyle: { type: "dashed", color: "#71717a" },
          itemStyle: { color: "#71717a" },
          showSymbol: false,
        },
      ],
    };
  }, [data, seasons, t]);

  if (seasons.length === 0) {
    return (
      <p className="text-small text-muted p-4">
        {t("no_data", "Keine Daten verfügbar")}
      </p>
    );
  }

  return (
    <div className="space-y-6 p-4 lg:p-5">
      {chartOption && <EChart option={chartOption} height={320} />}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-small">
          <thead>
            <tr>
              <th className="border border-border bg-surface-subtle px-3 py-2 text-left">
                {t("season", "Saison")}
              </th>
              <th className="border border-border bg-surface-subtle px-3 py-2 text-left">
                {t("league", "Liga")}
              </th>
              <th className="border border-border bg-surface-subtle px-3 py-2 text-center">
                {t("ranking", "Rang")}
              </th>
              <th className="border border-border bg-surface-subtle px-3 py-2 text-center">
                {t("ui.league_comparison.team_avg", "Mannschaft")}
              </th>
              <th className="border border-border bg-surface-subtle px-3 py-2 text-center">
                {t("ui.league_comparison.league_avg", "Liga")}
              </th>
              <th className="border border-border bg-surface-subtle px-3 py-2 text-center">
                {t("ui.league_comparison.diff", "Differenz")}
              </th>
            </tr>
          </thead>
          <tbody>
            {seasons.map((s) => {
              const row = data[s];
              const teamAvg = row.team_performance?.team_average_score;
              const leagueAvg = row.league_averages?.average_score;
              const diff = row.vs_league_average ?? row.team_performance?.vs_league_average;
              return (
                <tr key={s}>
                  <td className="border border-border px-3 py-2 font-mono">{s}</td>
                  <td className="border border-border px-3 py-2">{row.league_name}</td>
                  <td className="border border-border px-3 py-2 text-center font-mono tabular-nums">
                    {row.performance_rank ?? row.team_performance?.performance_rank ?? "—"}
                  </td>
                  <td className="border border-border px-3 py-2 text-center font-mono tabular-nums">
                    {teamAvg != null ? teamAvg.toFixed(1) : "—"}
                  </td>
                  <td className="border border-border px-3 py-2 text-center font-mono tabular-nums">
                    {leagueAvg != null ? leagueAvg.toFixed(1) : "—"}
                  </td>
                  <td
                    className={`border border-border px-3 py-2 text-center font-mono tabular-nums ${
                      diff != null && diff > 0
                        ? "text-success-fg"
                        : diff != null && diff < 0
                          ? "text-danger-fg"
                          : ""
                    }`}
                  >
                    {diff != null ? (diff > 0 ? `+${diff.toFixed(1)}` : diff.toFixed(1)) : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
