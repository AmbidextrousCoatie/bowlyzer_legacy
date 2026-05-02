import { useMemo } from "react";
import { EChart } from "../../../lib/charts/EChart";
import {
  buildWeekLabels,
  mutedTrendOption,
  scatterMultiAxisOption,
} from "../../../lib/charts/options";
import { DataTable } from "../../../lib/datatable/DataTable";
import {
  useTeamAnalysis,
  useTeamPerformanceTable,
  useTeamPoints,
  useTeamPositions,
  useTeamWinPercentageTable,
} from "../../../hooks/useLeague";
import { useTranslations } from "../../../hooks/useTranslations";

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

  const scoreBubbleOption = useMemo(() => {
    const perf = analysis.data?.performance_data?.data;
    if (!perf) return null;
    const order = analysis.data?.player_order_by_average ?? Object.keys(perf);
    return scatterMultiAxisOption(perf, order, buildWeekLabels(perf, weekLabel), {
      tooltipValueLabel: t("score", "Score"),
    });
  }, [analysis.data, weekLabel, t]);

  const winPercentageBubbleOption = useMemo(() => {
    const wp = analysis.data?.win_percentage_data;
    if (!wp) return null;
    const order = analysis.data?.player_order_by_average ?? Object.keys(wp);
    return scatterMultiAxisOption(wp, order, buildWeekLabels(wp, weekLabel), {
      tooltipValueLabel: t("win_percentage", "Win %"),
    });
  }, [analysis.data, weekLabel, t]);

  const pointsTrendOption = useMemo(() => {
    const data = points.data?.data_accumulated ?? points.data?.data;
    if (!data) return null;
    return mutedTrendOption(data, team, {
      yAxisName: t("points", "Punkte"),
      weekLabel,
    });
  }, [points.data, team, t, weekLabel]);

  const positionTrendOption = useMemo(() => {
    if (!positions.data?.data) return null;
    return mutedTrendOption(positions.data.data, team, {
      invertY: true,
      yAxisName: t("position", "Tabellenplatz"),
      weekLabel,
    });
  }, [positions.data, team, t, weekLabel]);

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
        <DataTableQuery
          query={performanceTable}
          options={{
            disablePositionCircle: false,
            enableSpecialRowStyling: true,
            tooltips: true,
            disableTeamColorUpdate: true,
          }}
        />
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
        <DataTableQuery
          query={winPercentageTable}
          options={{
            disablePositionCircle: false,
            enableSpecialRowStyling: true,
            tooltips: true,
            disableTeamColorUpdate: true,
          }}
        />
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
