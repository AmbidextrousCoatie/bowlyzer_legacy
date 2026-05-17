import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import { EChart } from "../../../lib/charts/EChart";
import { getSemanticColor } from "../../../lib/color-utils";
import type { ClutchAnalysis } from "../../../hooks/useTeam";

type Props = {
  data: ClutchAnalysis;
  threshold: number;
  onThresholdChange: (value: number) => void;
  t: (key: string, fallback?: string) => string;
};

export function ClutchAnalysisSection({
  data,
  threshold,
  onThresholdChange,
  t,
}: Props) {
  if (data.error || !data.opponent_clutch) {
    return (
      <p className="text-small text-muted p-4">
        {data.error ?? t("no_data", "Keine Daten verfügbar")}
      </p>
    );
  }

  const opponents = useMemo(
    () =>
      Object.entries(data.opponent_clutch ?? {}).sort(
        (a, b) => b[1].wins + b[1].losses - (a[1].wins + a[1].losses),
      ),
    [data.opponent_clutch],
  );

  const chartOption = useMemo<EChartsOption>(() => {
    const names = opponents.map(([n]) => n);
    const wins = opponents.map(([, v]) => v.wins);
    const losses = opponents.map(([, v]) => -v.losses);
    const maxAbs = Math.max(1, ...wins, ...losses.map((v) => Math.abs(v)));

    return {
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (params: unknown) => {
          const items = Array.isArray(params) ? params : [params];
          const idx = (items[0] as { dataIndex?: number })?.dataIndex ?? 0;
          const opponent = names[idx] ?? "";
          const winVal = wins[idx] ?? 0;
          const lossVal = Math.abs(losses[idx] ?? 0);
          const total = winVal + lossVal;
          const winRate = total > 0 ? ((winVal / total) * 100).toFixed(1) : "0";
          return [
            `<strong>${opponent}</strong>`,
            `${t("wins", "Siege")}: ${winVal}`,
            `${t("losses", "Niederlagen")}: ${lossVal}`,
            `${t("ui.clutch.total", "Gesamt")}: ${total}`,
            `${t("ui.clutch.win_pct", "Siege %")}: ${winRate}%`,
          ].join("<br/>");
        },
      },
      legend: {
        data: [t("wins", "Siege"), t("losses", "Niederlagen")],
        bottom: 0,
      },
      grid: { left: 120, right: 40, top: 16, bottom: 48, containLabel: true },
      xAxis: {
        type: "value",
        min: -maxAbs - 0.5,
        max: maxAbs + 0.5,
        axisLine: { show: true, lineStyle: { color: "#71717a" } },
        axisTick: { show: false },
        axisLabel: {
          formatter: (value: number) => String(Math.abs(Math.round(value))),
        },
        splitLine: {
          show: true,
          lineStyle: { type: "dashed", color: "rgba(0,0,0,0.12)" },
        },
      },
      yAxis: {
        type: "category",
        data: names,
        inverse: true,
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [
        {
          name: t("wins", "Siege"),
          type: "bar",
          stack: "total",
          data: wins,
          itemStyle: { color: getSemanticColor("positive") },
          label: {
            show: true,
            position: "right",
            formatter: (p) => {
              const v = typeof p.value === "number" ? p.value : Number(p.value);
              return Number.isFinite(v) && v > 0 ? String(v) : "";
            },
          },
        },
        {
          name: t("losses", "Niederlagen"),
          type: "bar",
          stack: "total",
          data: losses,
          itemStyle: { color: getSemanticColor("negative") },
          label: {
            show: true,
            position: "left",
            formatter: (p) => {
              const v = typeof p.value === "number" ? p.value : Number(p.value);
              return Number.isFinite(v) && v < 0 ? String(Math.abs(v)) : "";
            },
          },
        },
      ],
    };
  }, [opponents, t]);

  return (
    <div className="space-y-4 p-4 lg:p-5">
      <label className="flex flex-wrap items-center gap-2 text-small">
        <span className="text-muted">
          {t("ui.clutch.threshold", "Clutch-Schwelle (Punkte)")}
        </span>
        <input
          type="range"
          min={1}
          max={100}
          value={threshold}
          onChange={(e) => onThresholdChange(Number(e.target.value))}
          className="accent-accent"
        />
        <span className="font-mono tabular-nums w-6">{threshold}</span>
      </label>

      <dl className="grid gap-3 sm:grid-cols-4 text-small">
        <Stat label={t("ui.clutch.total_games", "Spiele gesamt")} value={data.total_games} />
        <Stat label={t("ui.clutch.clutch_games", "Clutch-Spiele")} value={data.total_clutch_games} />
        <Stat
          label={t("ui.clutch.win_pct", "Clutch-Siege %")}
          value={data.clutch_percentage != null ? `${data.clutch_percentage}%` : "—"}
        />
        <Stat
          label={t("ui.clutch.record", "S / N")}
          value={`${data.total_clutch_wins ?? 0} / ${data.total_clutch_losses ?? 0}`}
        />
      </dl>

      {opponents.length > 0 ? (
        <EChart option={chartOption} height={Math.max(280, opponents.length * 28)} />
      ) : (
        <p className="text-small text-muted">{t("no_data", "Keine Daten verfügbar")}</p>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number | undefined }) {
  return (
    <div className="rounded-sm border border-border bg-surface-subtle px-3 py-2">
      <dt className="text-label text-muted">{label}</dt>
      <dd className="font-mono tabular-nums text-h3 mt-0.5">{value ?? "—"}</dd>
    </div>
  );
}
