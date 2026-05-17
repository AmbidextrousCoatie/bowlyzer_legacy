import { useEffect, useMemo, useRef, useState } from "react";
import type { EChartsOption } from "echarts";
import { EChart } from "../../../lib/charts/EChart";
import { DataTable } from "../../../lib/datatable/DataTable";
import { getHeatMapColor, getSemanticColor } from "../../../lib/color-utils";
import { tournamentResultsTableOptions } from "../tournamentTableOptions";
import type {
  TournamentPlayerBestEfforts,
  TournamentPlayerCardId,
  TournamentPlayerSection as TournamentPlayerSectionData,
  TournamentPlayerSummary,
  TournamentProgressSeries,
} from "../../../hooks/useTournament";

type Props = {
  data: TournamentPlayerSectionData;
  heatmapEnabled: boolean;
  onToggleHeatmap: () => void;
  onBack: () => void;
  t: (key: string, fallback?: string) => string;
};

type CutMode = "dynamic" | "horizontal";

type HeatmapRange = {
  min?: number;
  max?: number;
  high_band_min?: number;
  high_band_max?: number;
  perfect_score?: number;
};

const DEFAULT_RANGE: Required<HeatmapRange> = {
  min: 130,
  max: 270,
  high_band_min: 271,
  high_band_max: 299,
  perfect_score: 300,
};

const DEFAULT_PLAYER_CARD_LAYOUT: TournamentPlayerCardId[] = [
  "summary_final_position",
  "summary_average",
  "summary_best_position",
  "best_highest_game",
  "best_highest_block",
];

const PLAYER_COLOR = "#2563eb";

function chunkBy<T>(arr: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) {
    out.push(arr.slice(i, i + size));
  }
  return out;
}

function PlayerMetricTile({
  id,
  summary,
  bestEfforts,
  t,
}: {
  id: TournamentPlayerCardId;
  summary: TournamentPlayerSummary;
  bestEfforts: TournamentPlayerBestEfforts;
  t: (key: string, fallback?: string) => string;
}) {
  switch (id) {
    case "summary_final_position":
      return (
        <Tile
          id="tournamentFinalPositionCard"
          label={t("ui.tournament.final_position", "Endplatz")}
          value={fmt(summary.final_position)}
          sub={t("ui.tournament.after_final_game", "Nach letztem Spiel")}
          highlight
        />
      );
    case "summary_average":
      return (
        <Tile
          label={t("ui.tournament.average", "Durchschnitt")}
          value={fmt(summary.average, 2)}
          sub={t("ui.tournament.cumulated", "Kumuliert")}
        />
      );
    case "summary_best_position":
      return (
        <Tile
          label={t("ui.tournament.best_position", "Beste Platzierung")}
          value={fmt(summary.best_position)}
          sub={summary.best_position_game ?? ""}
        />
      );
    case "best_highest_game":
      return (
        <Tile
          label={t("ui.tournament.highest_game", "Bestes Spiel")}
          value={fmt(bestEfforts.highest_game?.score)}
          sub={`${bestEfforts.highest_game?.stage ?? ""} ${
            bestEfforts.highest_game?.game ? `(G${bestEfforts.highest_game.game})` : ""
          }`.trim()}
        />
      );
    case "best_highest_pair":
      return (
        <Tile
          label={t("ui.tournament.highest_pair", "Bestes Paar")}
          value={fmt(bestEfforts.highest_pair?.score)}
          sub={`${bestEfforts.highest_pair?.stage ?? ""} ${
            bestEfforts.highest_pair?.pair ? `(${bestEfforts.highest_pair.pair})` : ""
          }`.trim()}
        />
      );
    case "handicap_profile":
      return (
        <Tile
          label={t("ui.tournament.player_handicap_card", "Handicap")}
          value={fmt(bestEfforts.handicap_profile?.handicap_per_game)}
          sub={[
            `${t("ui.tournament.apriori_avg_label", "Apriori-Schnitt")}: ${fmt(
              bestEfforts.handicap_profile?.a_priori_average,
              1,
            )}`,
            bestEfforts.handicap_profile?.handicap_reference != null
              ? `${t("ui.tournament.handicap_ref_label", "Referenz")}: ${fmt(
                  bestEfforts.handicap_profile.handicap_reference,
                  1,
                )}`
              : "",
          ]
            .filter(Boolean)
            .join(" · ")}
        />
      );
    case "best_highest_block":
      return (
        <Tile
          label={t("ui.tournament.highest_block", "Bester Block")}
          value={fmt(bestEfforts.highest_block?.score)}
          sub={bestEfforts.highest_block?.stage ?? ""}
        />
      );
    default:
      return null;
  }
}

export function PlayerSection({ data, heatmapEnabled, onToggleHeatmap, onBack, t }: Props) {
  const [cutMode, setCutMode] = useState<CutMode>("dynamic");
  const tableRef = useRef<HTMLDivElement>(null);

  const summary = data.summary ?? {};
  const bestEfforts = data.best_efforts ?? {};
  const series = data.progress_series ?? null;
  const cardLayout =
    data.player_card_layout && data.player_card_layout.length > 0
      ? data.player_card_layout
      : DEFAULT_PLAYER_CARD_LAYOUT;

  const avgOption = useMemo<EChartsOption | null>(
    () => buildAverageOption(series, data.player, cutMode, t),
    [series, data.player, cutMode, t],
  );
  const posOption = useMemo<EChartsOption | null>(
    () => buildPositionOption(series, data.player, t),
    [series, data.player, t],
  );

  const range = (
    data.round_table?.metadata as { heatmap_ranges?: { game_score?: HeatmapRange } } | undefined
  )?.heatmap_ranges?.game_score;

  useEffect(() => {
    let cancelled = false;
    let attempts = 0;
    const tick = () => {
      if (cancelled) return;
      const root = tableRef.current;
      const cells = root?.querySelectorAll<HTMLElement>(
        ".tabulator-cell[tabulator-field^='game_']",
      );
      if (!cells || cells.length === 0) {
        attempts += 1;
        if (attempts < 40) requestAnimationFrame(tick);
        return;
      }
      paintHeatmap(cells, heatmapEnabled, range);
    };
    requestAnimationFrame(tick);
    return () => {
      cancelled = true;
    };
  }, [data.round_table, heatmapEnabled, range]);

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <p className="text-label uppercase text-muted mb-1.5">
            {t("ui.tournament.player", "Spieler")}
          </p>
          <h2 className="text-h2">
            {data.player}
            {data.player_club ? (
              <span className="text-muted font-normal"> · {data.player_club}</span>
            ) : null}
          </h2>
        </div>
        <button
          type="button"
          onClick={onBack}
          className="h-9 rounded-sm border border-border bg-surface px-3 text-small font-medium hover:border-border-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          {t("ui.tournament.back_to_overview", "Zurück zur Übersicht")}
        </button>
      </div>

      {chunkBy(cardLayout, 3).map((row, ri) => (
        <div
          key={ri}
          className={
            ri === 0
              ? "grid grid-cols-1 gap-x-12 gap-y-6 md:grid-cols-3"
              : "mt-8 grid grid-cols-1 gap-x-12 gap-y-6 md:grid-cols-3"
          }
        >
          {row.map((id) => (
            <PlayerMetricTile key={`${ri}-${id}`} id={id} summary={summary} bestEfforts={bestEfforts} t={t} />
          ))}
        </div>
      ))}

      <div className="mt-12 grid grid-cols-1 gap-8 lg:grid-cols-2">
        <div>
          <div className="mb-3 flex items-baseline justify-between gap-3">
            <p className="text-label uppercase text-muted">
              {t("ui.tournament.cum_avg_over_games", "Schnitt pro Spiel")}
            </p>
            <button
              type="button"
              onClick={() => setCutMode((m) => (m === "dynamic" ? "horizontal" : "dynamic"))}
              className="h-7 rounded-sm border border-border bg-surface px-2.5 text-caption hover:border-border-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              {t("ui.tournament.cut", "Cut")} ·{" "}
              {cutMode === "dynamic"
                ? t("ui.tournament.dynamic", "Dynamisch")
                : t("ui.tournament.static", "Statisch")}
            </button>
          </div>
          {avgOption ? (
            <div className="rounded-sm border border-border bg-surface p-3">
              <EChart option={avgOption} height={300} />
            </div>
          ) : (
            <NoChartFrame t={t} />
          )}
        </div>
        <div>
          <p className="text-label uppercase text-muted mb-3">
            {t("ui.tournament.cum_pos_over_games", "Platzierung pro Spiel")}
          </p>
          {posOption ? (
            <div className="rounded-sm border border-border bg-surface p-3">
              <EChart option={posOption} height={300} />
            </div>
          ) : (
            <NoChartFrame t={t} />
          )}
        </div>
      </div>

      <div className="mt-12">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
          <h3 className="text-h3">{t("ui.tournament.results", "Ergebnisse")}</h3>
          <button
            type="button"
            onClick={onToggleHeatmap}
            aria-pressed={heatmapEnabled}
            className={
              "h-9 rounded-sm border px-3 text-small font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring " +
              (heatmapEnabled
                ? "border-accent bg-accent text-accent-foreground hover:bg-accent-hover"
                : "border-border bg-surface text-foreground hover:border-border-strong")
            }
          >
            {t("ui.tournament.heatmap", "Heatmap")} ·{" "}
            {heatmapEnabled ? t("ui.common.on", "An") : t("ui.common.off", "Aus")}
          </button>
        </div>
        <div ref={tableRef}>
          <DataTable
            data={data.round_table}
            options={tournamentResultsTableOptions}
          />
        </div>
      </div>
    </section>
  );
}

function Tile({
  label,
  value,
  sub,
  highlight,
  id,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
  id?: string;
}) {
  return (
    <div
      id={id}
      className={
        "rounded-sm border p-4 " +
        (highlight ? "border-accent bg-accent-tint" : "border-border bg-surface")
      }
    >
      <p className="text-label uppercase text-muted mb-1.5">{label}</p>
      <p className="text-stat-md font-mono font-semibold tabular-nums text-foreground">{value}</p>
      {sub ? <p className="text-caption text-muted mt-1">{sub}</p> : null}
    </div>
  );
}

function NoChartFrame({ t }: { t: (key: string, fallback?: string) => string }) {
  return (
    <div className="grid place-items-center rounded-sm border border-dashed border-border p-6 text-small text-muted">
      {t("ui.tournament.no_progress", "Kein Verlauf vorhanden.")}
    </div>
  );
}

function fmt(value: number | string | null | undefined, decimals?: number): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "—";
    return decimals !== undefined ? value.toFixed(decimals) : String(value);
  }
  return String(value);
}

function paintHeatmap(
  cells: NodeListOf<HTMLElement>,
  enabled: boolean,
  range: HeatmapRange | undefined,
): void {
  const r = { ...DEFAULT_RANGE, ...range };
  cells.forEach((cell) => {
    cell.style.removeProperty("background-color");
    cell.style.removeProperty("font-weight");
    cell.style.removeProperty("color");
    cell.style.removeProperty("box-shadow");
    if (!enabled) return;
    const text = (cell.textContent ?? "").trim();
    if (!text) return;
    const value = parseFloat(text);
    if (!Number.isFinite(value)) return;
    if (value === r.perfect_score) {
      cell.style.setProperty("background-color", "#ffc107", "important");
      cell.style.setProperty("font-weight", "800", "important");
      cell.style.setProperty("color", "#111827", "important");
      cell.style.setProperty("box-shadow", "inset 0 0 0 2px #b77900", "important");
      return;
    }
    if (value >= r.high_band_min && value <= r.high_band_max) {
      cell.style.setProperty("background-color", "#ffe7a3", "important");
      cell.style.setProperty("font-weight", "600", "important");
      cell.style.setProperty("color", "#1f2933", "important");
      return;
    }
    const color = getHeatMapColor(value, r.min, r.max);
    cell.style.setProperty("background-color", color, "important");
    cell.style.setProperty("color", "#1f2933", "important");
  });
}

function buildAverageOption(
  series: TournamentProgressSeries | null,
  playerName: string,
  cutMode: CutMode,
  t: (key: string, fallback?: string) => string,
): EChartsOption | null {
  if (!series || !series.labels || series.labels.length === 0) return null;
  const totalGames = series.labels.length;
  const avg = (series.avg_series ?? []).map((v) => (v == null ? null : Number(v)));
  const leader = (series.tournament_leader_avg_series ?? []).map((v) =>
    v == null ? null : Number(v),
  );
  const cutLineSeries = series.cut_line_series ?? [];
  const cutValues = (series.cut_lines_avg ?? []).map((v) => (v == null ? null : Number(v)));

  const collectNumbers = (...arrs: Array<Array<number | null>>) =>
    arrs.flat().filter((v): v is number => v != null && Number.isFinite(v));
  const flatCut = cutLineSeries
    .flatMap((c) => c.data ?? [])
    .map((v) => (v == null ? null : Number(v)));
  const all = collectNumbers(avg, leader, flatCut);
  let yMin = 150;
  let yMax = 250;
  if (all.length > 0) {
    const minVal = Math.min(...all);
    const maxVal = Math.max(...all);
    const padding = Math.max(3, (maxVal - minVal) * 0.05);
    yMin = Math.floor((minVal - padding) / 5) * 5;
    yMax = Math.ceil((maxVal + padding) / 5) * 5;
    yMin = Math.max(120, yMin);
    yMax = Math.min(300, yMax);
    if (yMax <= yMin) yMax = yMin + 10;
  }

  const cutColor = getSemanticColor("negative");
  const leaderColor = "#7c3aed";

  const dynamicCut = (() => {
    if (cutMode !== "dynamic" || cutLineSeries.length === 0) return [];
    const sorted = [...cutLineSeries].sort(
      (a, b) => Number(a.round_number ?? 0) - Number(b.round_number ?? 0),
    );
    const segments: Array<Array<[number, number]>> = [];
    sorted.forEach((line) => {
      const pts: Array<[number, number]> = [];
      (line.data ?? []).forEach((raw, i) => {
        if (raw == null) return;
        const n = Number(raw);
        if (!Number.isFinite(n)) return;
        const y = Math.max(yMin, Math.min(yMax, n));
        pts.push([i + 1, y]);
      });
      if (pts.length) segments.push(pts);
    });
    if (!segments.length) return [];
    const stitched: Array<[number, number]> = [...segments[0]];
    for (let i = 1; i < segments.length; i += 1) {
      const prev = segments[i - 1];
      const next = segments[i];
      const prevLast = prev[prev.length - 1];
      const nextFirst = next[0];
      const boundaryX = (prevLast[0] + nextFirst[0]) / 2;
      stitched.push([boundaryX, prevLast[1]]);
      stitched.push([boundaryX, nextFirst[1]]);
      stitched.push(...next);
    }
    return [
      {
        name: t("ui.tournament.cut_line_pace", "Cut-Line (Pace)"),
        type: "line" as const,
        data: stitched,
        showSymbol: false,
        smooth: false,
        connectNulls: false,
        lineStyle: { width: 2, type: "dashed" as const, color: cutColor },
        itemStyle: { color: cutColor },
        z: 1,
      },
    ];
  })();

  const horizontalCutMarkLines =
    cutMode === "horizontal" && cutValues.some((v) => v != null)
      ? cutValues
          .filter((v): v is number => v != null && Number.isFinite(v))
          .map((v) => ({
            yAxis: Math.max(yMin, Math.min(yMax, v)),
            lineStyle: { color: cutColor, type: "dashed" as const, width: 2 },
          }))
      : [];

  const playerSeries = {
    name: playerName,
    type: "line" as const,
    data: avg.map((v, i) => [i + 1, v == null ? null : Math.max(yMin, Math.min(yMax, v))]),
    showSymbol: false,
    smooth: false,
    connectNulls: false,
    lineStyle: { width: 2, color: PLAYER_COLOR },
    itemStyle: { color: PLAYER_COLOR },
    markLine: horizontalCutMarkLines.length
      ? {
          symbol: ["none", "none"] as [string, string],
          silent: true,
          label: { show: false },
          data: horizontalCutMarkLines,
        }
      : undefined,
    z: 3,
  };

  const leaderSeries =
    leader.length && leader.some((v) => v != null)
      ? [
          {
            name: t("ui.tournament.tournament_leader", "Turnierführung"),
            type: "line" as const,
            data: leader.map((v, i) => [
              i + 1,
              v == null ? null : Math.max(yMin, Math.min(yMax, v)),
            ]),
            showSymbol: false,
            smooth: false,
            lineStyle: { width: 2, type: "dashed" as const, color: leaderColor },
            itemStyle: { color: leaderColor },
            z: 1,
          },
        ]
      : [];

  return {
    animation: false,
    tooltip: {
      trigger: "axis",
      formatter: (raw: unknown) => formatTooltip(raw, series, t, false),
    },
    legend: { show: true, top: 0, textStyle: { fontSize: 11 } },
    grid: { top: 30, right: 16, bottom: 40, left: 50, containLabel: true },
    xAxis: {
      type: "value",
      min: 0,
      max: totalGames + 0.5,
      name: t("ui.tournament.game", "Spiel"),
      nameLocation: "middle",
      nameGap: 28,
      interval: 1,
      axisLabel: {
        formatter: (value: number) =>
          Number.isInteger(value) && value >= 1 && value <= totalGames ? String(value) : "",
      },
    },
    yAxis: {
      type: "value",
      name: t("ui.tournament.average", "Durchschnitt"),
      min: yMin,
      max: yMax,
    },
    series: [playerSeries, ...leaderSeries, ...dynamicCut],
  };
}

function buildPositionOption(
  series: TournamentProgressSeries | null,
  playerName: string,
  t: (key: string, fallback?: string) => string,
): EChartsOption | null {
  if (!series || !series.labels || series.labels.length === 0) return null;
  const totalGames = series.labels.length;
  const positions = (series.position_series ?? []).map((v) => (v == null ? null : Number(v)));
  const cutValues = (series.cut_lines_position ?? []).map((v) => (v == null ? null : Number(v)));

  const finitePositions = positions.filter((v): v is number => v != null && Number.isFinite(v));
  const yMin = 1;
  const maxObservedRank = finitePositions.length ? Math.max(...finitePositions) : 1;
  const participants = Number(series.participant_count);
  const rankCap =
    Number.isFinite(participants) && participants > 0
      ? Math.max(participants, maxObservedRank)
      : maxObservedRank;
  const yMax = Math.max(1, Math.ceil(rankCap));

  const cutColor = getSemanticColor("negative");
  const cutMarks = cutValues
    .filter((v): v is number => v != null && Number.isFinite(v))
    .map((v) => ({
      yAxis: Math.max(yMin, Math.min(yMax, v)),
      lineStyle: { color: cutColor, type: "dashed" as const, width: 2 },
    }));

  return {
    animation: false,
    tooltip: {
      trigger: "axis",
      formatter: (raw: unknown) => formatTooltip(raw, series, t, true),
    },
    grid: { top: 16, right: 16, bottom: 40, left: 50, containLabel: true },
    xAxis: {
      type: "value",
      min: 0,
      max: totalGames + 0.5,
      name: t("ui.tournament.game", "Spiel"),
      nameLocation: "middle",
      nameGap: 28,
      interval: 1,
      axisLabel: {
        formatter: (value: number) =>
          Number.isInteger(value) && value >= 1 && value <= totalGames ? String(value) : "",
      },
    },
    yAxis: {
      type: "value",
      name: t("ui.tournament.rank", "Platz"),
      min: yMin,
      max: yMax,
      inverse: true,
    },
    series: [
      {
        name: playerName,
        type: "line",
        data: positions.map((v, i) => [i + 1, v]),
        showSymbol: false,
        smooth: false,
        lineStyle: { width: 2, color: PLAYER_COLOR },
        itemStyle: { color: PLAYER_COLOR },
        markLine: cutMarks.length
          ? {
              symbol: ["none", "none"],
              silent: true,
              label: { show: false },
              data: cutMarks,
            }
          : undefined,
        z: 2,
      },
    ],
  };
}

function formatTooltip(
  raw: unknown,
  series: TournamentProgressSeries,
  t: (key: string, fallback?: string) => string,
  isRank: boolean,
): string {
  const params = raw as Array<{
    seriesName: string;
    value: [number, number | null];
    marker: string;
    axisValue: number;
  }>;
  if (!Array.isArray(params) || params.length === 0) return "";
  const sorted = [...params].sort((a, b) => {
    const av = a.value?.[1];
    const bv = b.value?.[1];
    if (av == null) return 1;
    if (bv == null) return -1;
    return isRank ? av - bv : bv - av;
  });
  const gameNo = Math.round(sorted[0].axisValue);
  const score = series.game_score_series?.[gameNo - 1] ?? null;
  const head =
    `${t("ui.tournament.game", "Spiel")} ${gameNo}: ` + (score == null ? "—" : String(score));
  const lines = sorted.map((p) => {
    const v = p.value?.[1];
    const valStr = v == null ? "—" : isRank ? String(Math.round(v)) : v.toFixed(1);
    return `${p.marker}${p.seriesName}: <b>${valStr}</b>`;
  });
  return [head, ...lines].join("<br/>");
}
