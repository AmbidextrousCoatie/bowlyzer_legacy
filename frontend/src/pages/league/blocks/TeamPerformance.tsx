import { useEffect, useMemo } from "react";
import { EChart } from "../../../lib/charts/EChart";
import {
  buildWeekLabels,
  mutedTrendOption,
  scatterMultiAxisOption,
  type SeriesData,
} from "../../../lib/charts/options";
import {
  getTeamPerformanceHighlightColor,
  seedPlayerColorsFromPerformanceOrder,
} from "../../../lib/color-utils";
import { normalizeUnicodeLabel } from "../../../lib/teamUtils";
import { DataTable } from "../../../lib/datatable/DataTable";
import type { DataTableOptions } from "../../../lib/datatable/types";
import {
  useTeamAnalysis,
  useTeamPerformanceTable,
  useTeamPoints,
  useTeamPositions,
  useTeamWinPercentageTable,
} from "../../../hooks/useLeague";
import { useTranslations } from "../../../hooks/useTranslations";

const TEAM_PERFORMANCE_ALIASES = (teamName: string) => [
  teamName,
  `${teamName} (Team)`,
  `${teamName} (Team Average)`,
];

/** Key used in SeriesData payloads (must match backend team row). */
function resolveTeamDataKey(seriesData: SeriesData, teamKey: string): string {
  const keys = Object.keys(seriesData);
  const normalized = normalizeUnicodeLabel(teamKey);
  if (keys.includes(teamKey)) return teamKey;
  const match = keys.find((k) => normalizeUnicodeLabel(k) === normalized);
  return match ?? teamKey;
}

/** Players first (by average rank), team summary row last — matches performance tables. */
function buildTeamPerformanceChartOrder(
  seriesData: SeriesData,
  playerOrder: string[] | undefined,
  teamKey: string,
): string[] {
  const dataTeamKey = resolveTeamDataKey(seriesData, teamKey);
  const dataKeys = new Set(Object.keys(seriesData));
  const players =
    playerOrder?.filter((name) => dataKeys.has(name)) ??
    [...dataKeys].filter((name) => name !== dataTeamKey).sort((a, b) => a.localeCompare(b));
  const order = [...players];
  if (dataKeys.has(dataTeamKey) && !order.includes(dataTeamKey)) {
    order.push(dataTeamKey);
  }
  return order;
}

function scatterPerformanceOptions(
  playerOrder: string[] | undefined,
  teamKey: string,
  tooltipValueLabel: string,
) {
  const perfColors =
    playerOrder?.length && teamKey
      ? { playerOrder, teamKey }
      : undefined;
  return {
    tooltipValueLabel,
    usePlayerColors: true as const,
    performanceColors: perfColors,
  };
}

type Props = {
  season: string;
  league: string;
  team: string;
};

/** Visible when league + season + team (no week, no round). */
export function TeamPerformance({ season, league, team }: Props) {
  const { t } = useTranslations();
  const weekLabel = t("week", "Spieltag");

  const performanceTable = useTeamPerformanceTable(season, league, team);
  const winPercentageTable = useTeamWinPercentageTable(season, league, team);
  const analysis = useTeamAnalysis(season, league, team);
  const points = useTeamPoints(season, league);
  const positions = useTeamPositions(season, league);

  const playerOrder = analysis.data?.player_order_by_average;
  const teamKey = normalizeUnicodeLabel(analysis.data?.team ?? team);

  const teamHighlightColor = useMemo(() => {
    if (!playerOrder?.length || !teamKey) return undefined;
    return getTeamPerformanceHighlightColor(playerOrder, teamKey);
  }, [playerOrder, teamKey]);

  useEffect(() => {
    if (playerOrder?.length) {
      seedPlayerColorsFromPerformanceOrder(playerOrder, teamKey, TEAM_PERFORMANCE_ALIASES(teamKey));
    }
  }, [playerOrder, teamKey]);

  const teamPerformanceTableOptions = useMemo((): DataTableOptions => {
    const base: DataTableOptions = {
      disablePositionCircle: false,
      enableSpecialRowStyling: true,
      tooltips: true,
      disableTeamColorUpdate: true,
      performanceTeamName: teamKey,
    };
    if (playerOrder?.length) {
      return { ...base, playerColorOrder: playerOrder };
    }
    return base;
  }, [teamKey, playerOrder]);

  const scoreBubbleOption = useMemo(() => {
    const perf = analysis.data?.performance_data?.data;
    if (!perf) return null;
    if (playerOrder?.length) {
      seedPlayerColorsFromPerformanceOrder(playerOrder, teamKey, TEAM_PERFORMANCE_ALIASES(teamKey));
    }
    const order = buildTeamPerformanceChartOrder(perf, playerOrder, teamKey);
    return scatterMultiAxisOption(
      perf,
      order,
      buildWeekLabels(perf, weekLabel),
      scatterPerformanceOptions(playerOrder, teamKey, t("score", "Score")),
    );
  }, [analysis.data, playerOrder, teamKey, weekLabel, t]);

  const winPercentageBubbleOption = useMemo(() => {
    const wpRaw = analysis.data?.win_percentage_data;
    let wp: Record<string, number[]> | undefined;
    if (wpRaw && typeof wpRaw === "object" && "data" in wpRaw) {
      const nested = (wpRaw as { data?: Record<string, number[]> }).data;
      wp = nested && typeof nested === "object" ? nested : undefined;
    } else if (wpRaw && typeof wpRaw === "object") {
      wp = wpRaw as Record<string, number[]>;
    }
    if (!wp) return null;
    if (playerOrder?.length) {
      seedPlayerColorsFromPerformanceOrder(playerOrder, teamKey, TEAM_PERFORMANCE_ALIASES(teamKey));
    }
    const order = buildTeamPerformanceChartOrder(wp, playerOrder, teamKey);
    return scatterMultiAxisOption(
      wp,
      order,
      buildWeekLabels(wp, weekLabel),
      scatterPerformanceOptions(playerOrder, teamKey, t("win_percentage", "Win %")),
    );
  }, [analysis.data, playerOrder, teamKey, weekLabel, t]);

  const pointsTrendOption = useMemo(() => {
    const data = points.data?.data_accumulated ?? points.data?.data;
    if (!data) return null;
    const teamOrder = points.data?.sorted_by_total ?? Object.keys(data);
    return mutedTrendOption(data, teamKey, {
      yAxisName: t("points", "Punkte"),
      weekLabel,
      teamOrder,
      league,
      selectedColor: teamHighlightColor,
    });
  }, [points.data, teamKey, t, weekLabel, league, teamHighlightColor]);

  const positionTrendOption = useMemo(() => {
    if (!positions.data?.data) return null;
    const teamOrder =
      positions.data.sorted_by_best ??
      positions.data.sorted_by_total ??
      Object.keys(positions.data.data);
    return mutedTrendOption(positions.data.data, teamKey, {
      invertY: true,
      yAxisName: t("position", "Tabellenplatz"),
      weekLabel,
      teamOrder,
      league,
      selectedColor: teamHighlightColor,
    });
  }, [positions.data, teamKey, t, weekLabel, league, teamHighlightColor]);

  return (
    <div className="space-y-12">
      <header className="mb-2">
        <p className="text-label uppercase text-muted mb-1.5">
          {team} · {league} · {season}
        </p>
        <h2 className="text-h2">{t("ui.team_performance.title", "Mannschaftsanalyse")}</h2>
      </header>

      <Section
        eyebrow={t("ui.team_performance.individual", "Spieler")}
        title={t("performance_table", "Leistung pro Spieltag")}
      >
        <DataTableQuery query={performanceTable} options={teamPerformanceTableOptions} />
      </Section>

      <div className="grid grid-cols-1 gap-12 lg:grid-cols-2">
        <Section
          eyebrow={t("score_per_match_day", "Score pro Spieltag")}
          title={t("score_bubble", "Spielerwerte")}
        >
          <ChartFrame
            isPending={analysis.isPending}
            isError={analysis.isError}
            errorMessage={analysis.error?.message}
            option={scoreBubbleOption}
            height={380}
          />
        </Section>
        <Section
          eyebrow={t("ui.win_percentage.weekly", "Wöchentliche Siegquote")}
          title={t("win_pct_bubble", "Siegquote pro Spieltag")}
        >
          <ChartFrame
            isPending={analysis.isPending}
            isError={analysis.isError}
            errorMessage={analysis.error?.message}
            option={winPercentageBubbleOption}
            height={380}
          />
        </Section>
      </div>

      <div className="grid grid-cols-1 gap-12 lg:grid-cols-2">
        <Section
          eyebrow={t("points_in_season_progress", "Punkte kumuliert")}
          title={t("league_context", "Liga-Kontext")}
        >
          <ChartFrame
            isPending={points.isPending}
            isError={points.isError}
            errorMessage={points.error?.message}
            option={pointsTrendOption}
            height={300}
          />
        </Section>
        <Section
          eyebrow={t("position_in_season_progress", "Tabellenplatz")}
          title={t("league_context", "Liga-Kontext")}
        >
          <ChartFrame
            isPending={positions.isPending}
            isError={positions.isError}
            errorMessage={positions.error?.message}
            option={positionTrendOption}
            height={300}
          />
        </Section>
      </div>

      <Section
        eyebrow={t("ui.win_percentage.individual", "Siegquote pro Spieler")}
        title={t("win_pct_table", "Siegquoten-Tabelle")}
      >
        <DataTableQuery query={winPercentageTable} options={teamPerformanceTableOptions} />
      </Section>
    </div>
  );
}

function Section({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-4">
        <p className="text-label uppercase text-muted mb-1.5">{eyebrow}</p>
        <h2 className="text-h2">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function DataTableQuery({
  query,
  options,
}: {
  query: {
    data: import("../../../lib/datatable/types").TableData | undefined;
    isPending: boolean;
    isError: boolean;
    error: Error | null;
  };
  options: import("../../../lib/datatable/types").DataTableOptions;
}) {
  if (query.isPending) {
    return <div className="h-48 rounded-sm border border-border bg-surface-subtle" />;
  }
  if (query.isError) {
    return (
      <div className="rounded-sm border border-danger-fg/40 bg-surface p-6 text-small text-danger-fg">
        {query.error?.message ?? "Fehler beim Laden"}
      </div>
    );
  }
  if (!query.data || !query.data.columns || !query.data.data) {
    return (
      <div className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
        Keine Daten vorhanden.
      </div>
    );
  }
  return <DataTable data={query.data} options={options} />;
}

function ChartFrame({
  isPending,
  isError,
  errorMessage,
  option,
  height,
}: {
  isPending: boolean;
  isError: boolean;
  errorMessage?: string;
  option: import("echarts").EChartsOption | null;
  height: number;
}) {
  if (isPending) {
    return <div className="rounded-sm border border-border bg-surface-subtle" style={{ height }} />;
  }
  if (isError) {
    return (
      <div className="rounded-sm border border-danger-fg/40 bg-surface p-6 text-small text-danger-fg">
        {errorMessage ?? "Fehler beim Laden"}
      </div>
    );
  }
  if (!option) {
    return (
      <div
        className="grid place-items-center rounded-sm border border-dashed border-border text-small text-muted"
        style={{ height }}
      >
        Keine Daten vorhanden.
      </div>
    );
  }
  return (
    <div className="rounded-sm border border-border bg-surface p-3">
      <EChart option={option} height={height - 24} />
    </div>
  );
}
