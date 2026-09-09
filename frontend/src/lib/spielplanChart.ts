import type { EChartsOption } from "echarts";
import type { SpielplanChartModel, SpielplanChartPoint } from "./seasonSpielplan";
import { formatSpielplanDate } from "./seasonSpielplan";

function labelInk(hex: string): string {
  const raw = hex.replace("#", "");
  if (raw.length !== 6) return "#FAFAFA";
  const n = Number.parseInt(raw, 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return luminance > 160 ? "#18181B" : "#FAFAFA";
}

function axisInk(): { fg: string; muted: string; line: string } {
  if (typeof document === "undefined") {
    return { fg: "#18181B", muted: "#71717A", line: "#E4E4E7" };
  }
  const styles = getComputedStyle(document.documentElement);
  return {
    fg: styles.getPropertyValue("--ds-foreground").trim() || "#18181B",
    muted: styles.getPropertyValue("--ds-muted").trim() || "#71717A",
    line: styles.getPropertyValue("--ds-border").trim() || "#E4E4E7",
  };
}

/** Capsule with semicircle ends — same language as the filled circles on line charts. */
export const SPIELPLAN_PILL_SYMBOL = "path://M25,0L75,0A25,25,0,0,1,75,50L25,50A25,25,0,0,1,25,0Z";

/** One size for every venue chip: wide enough for three letters. */
export const SPIELPLAN_PILL_SIZE: [number, number] = [44, 28];

export function spielplanChartHeight(leagueCount: number): number {
  return Math.max(280, 48 + leagueCount * 36 + 40);
}

export function spielplanChartOption(
  model: SpielplanChartModel,
  t: (key: string, fallback?: string) => string,
  language: "de" | "en",
): EChartsOption | null {
  if (model.leagueLabels.length === 0 || model.dateLabels.length === 0) return null;
  const ink = axisInk();

  const dateGuides = {
    silent: true,
    symbol: "none" as const,
    animation: false,
    label: { show: false },
    lineStyle: {
      type: "dashed" as const,
      color: ink.muted,
      width: 1,
      opacity: 0.45,
    },
    data: model.dateKeys.map((dateKey) => ({ xAxis: dateKey })),
  };

  const series = model.venues.map((venue, index) => {
    const points = model.points.filter((point) => point.venueKey === venue.venueKey);
    return {
      name: `${venue.abbrev} = ${venue.displayName}`,
      type: "scatter" as const,
      data: points.map((point) => ({
        value: [point.dateKey, point.leagueShort],
        ...point,
      })),
      symbol: SPIELPLAN_PILL_SYMBOL,
      symbolKeepAspect: false,
      symbolSize: SPIELPLAN_PILL_SIZE,
      cursor: "pointer",
      clip: false,
      itemStyle: {
        color: venue.color,
        borderColor: venue.color,
        borderWidth: 2,
      },
      label: {
        show: true,
        position: "inside" as const,
        formatter: venue.abbrev,
        fontSize: 11,
        fontWeight: 600,
        fontFamily: "JetBrains Mono, ui-monospace, monospace",
        color: labelInk(venue.color),
      },
      emphasis: { scale: 1.08 },
      ...(index === 0 ? { markLine: dateGuides } : {}),
    };
  });

  return {
    animationDuration: 240,
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (raw) => formatSpielplanTooltip(raw, model, t, language),
    },
    legend: { show: false },
    grid: {
      top: 8,
      right: 12,
      bottom: 8,
      left: 8,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: model.dateKeys,
      axisLine: { show: true, onZero: false, lineStyle: { color: ink.line } },
      axisTick: { show: true, alignWithLabel: true, lineStyle: { color: ink.line } },
      axisLabel: {
        color: ink.muted,
        fontSize: 11,
        rotate: model.dateLabels.length > 10 ? 45 : 0,
        fontFamily: "JetBrains Mono, ui-monospace, monospace",
        formatter: (value: string) => {
          const index = model.dateKeys.indexOf(value);
          return model.dateLabels[index] ?? value;
        },
      },
      splitLine: { show: false },
    },
    yAxis: {
      type: "category",
      data: model.leagueLabels,
      inverse: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: ink.fg,
        fontSize: 11,
        fontFamily: "JetBrains Mono, ui-monospace, monospace",
      },
      splitLine: { show: false },
    },
    series,
  };
}

function formatSpielplanTooltip(
  raw: unknown,
  model: SpielplanChartModel,
  t: (key: string, fallback?: string) => string,
  language: "de" | "en",
): string {
  const params = raw as { data?: SpielplanChartPoint };
  const point = params.data;
  if (!point?.dateKey) return "";
  const { weekday, displayDate } = formatSpielplanDate(point.dateKey, language);
  const sameDay = model.eventsByDate[point.dateKey] ?? [];
  const leagues = sameDay
    .map((event) => {
      const mark = event.league === point.league ? "<strong>" : "";
      const end = event.league === point.league ? "</strong>" : "";
      return `${mark}${event.leagueShort} · ${t("week", "Spieltag")} ${event.week}${end}`;
    })
    .join("<br/>");
  return [
    `<div style="font-family:Inter,sans-serif;font-size:12px;line-height:1.45">`,
    `<div style="font-variant-numeric:tabular-nums">${weekday} ${displayDate}</div>`,
    `<div>${point.abbrev} = ${point.venueName}</div>`,
    `<div style="margin-top:6px;opacity:.72">${t("ui.league.spielplan_tooltip_leagues", "Ligen an diesem Tag")}</div>`,
    leagues,
    `</div>`,
  ].join("");
}

export function spielplanPointFromEvent(data: unknown): SpielplanChartPoint | null {
  if (!data || typeof data !== "object") return null;
  const point = data as Partial<SpielplanChartPoint>;
  if (!point.league || point.week == null) return null;
  return point as SpielplanChartPoint;
}
