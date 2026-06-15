import { useMemo } from "react";
import { lineChartOption } from "../../../lib/charts/options";
import {
  useLeagueAveragesHistory,
  usePointsToWinHistory,
  useRecordGames,
  useRecordIndividualGames,
  useRecordTeamGames,
  useTopIndividualPerformances,
  useTopTeamPerformances,
  type LeagueHistoryChart,
} from "../../../hooks/useLeague";
import { useTranslations } from "../../../hooks/useTranslations";
import type { DataTableOptions } from "../../../lib/datatable/types";
import { ChartFrame, DataTableSection, Section } from "./leagueBlockUi";

type Props = {
  league: string;
};

/**
 * F1 — league selected, no season (Alle Saisons): cross-season aggregation block.
 * See docs/RESPONSIVE_DATA_SPECIFICATION.md → LeagueAggregationBlock.
 */
export function LeagueOverview({ league }: Props) {
  const { t } = useTranslations();

  const averagesHistory = useLeagueAveragesHistory(league);
  const pointsToWin = usePointsToWinHistory(league);
  const topTeams = useTopTeamPerformances(league);
  const topIndividuals = useTopIndividualPerformances(league);
  const recordGames = useRecordGames(league);
  const recordIndividualGames = useRecordIndividualGames(league);
  const recordTeamGames = useRecordTeamGames(league);

  const averagesOption = useMemo(
    () => seasonHistoryChartOption(averagesHistory.data, league),
    [averagesHistory.data, league],
  );
  const pointsOption = useMemo(
    () => seasonHistoryChartOption(pointsToWin.data, league),
    [pointsToWin.data, league],
  );

  const basicTableOptions = useMemo<DataTableOptions>(
    () => ({
      disablePositionCircle: true,
      enableSpecialRowStyling: true,
      tooltips: true,
    }),
    [],
  );

  return (
    <div className="space-y-12">
      <div className="grid grid-cols-1 gap-12 lg:grid-cols-2">
        <Section
          eyebrow={t("history", "Verlauf")}
          title={t("ui.league.performance_all_seasons", "Liga-Leistung über alle Saisons")}
        >
          <ChartFrame
            isPending={averagesHistory.isPending}
            isError={averagesHistory.isError}
            errorMessage={averagesHistory.error?.message}
            option={averagesOption}
          />
        </Section>
        <Section
          eyebrow={t("cumulative_points", "Kumulative Punkte")}
          title={t("ui.league.points_to_win", "Punkte zum Sieg")}
        >
          <ChartFrame
            isPending={pointsToWin.isPending}
            isError={pointsToWin.isError}
            errorMessage={pointsToWin.error?.message}
            option={pointsOption}
          />
        </Section>
      </div>

      <Section
        eyebrow={t("top_team_performances", "Top Team-Leistungen")}
        title={t("top_team_performances", "Top Team-Leistungen")}
      >
        <DataTableSection query={topTeams} options={basicTableOptions} />
      </Section>

      <Section
        eyebrow={t("top_individual_performances", "Top Einzel-Leistungen")}
        title={t("top_individual_performances", "Top Einzel-Leistungen")}
      >
        <DataTableSection query={topIndividuals} options={basicTableOptions} />
      </Section>

      <div className="grid grid-cols-1 gap-12 lg:grid-cols-2">
        <Section eyebrow={t("record_games", "Rekordspiele")} title={t("team", "Mannschaft")}>
          <DataTableSection query={recordTeamGames} options={basicTableOptions} />
        </Section>
        <Section eyebrow={t("record_games", "Rekordspiele")} title={t("player", "Spieler")}>
          <DataTableSection query={recordIndividualGames} options={basicTableOptions} />
        </Section>
      </div>

      <Section eyebrow={t("record_games", "Rekordspiele")} title={t("record_games", "Rekordspiele")}>
        <DataTableSection query={recordGames} options={basicTableOptions} />
      </Section>
    </div>
  );
}

function seasonHistoryChartOption(
  payload: LeagueHistoryChart | undefined,
  league: string,
): import("echarts").EChartsOption | null {
  if (!payload?.data) return null;
  const labels = payload.labels ?? payload.seasons ?? [];
  if (!labels.length) return null;
  const seriesKeys = Object.keys(payload.data);
  if (!seriesKeys.length) return null;
  return lineChartOption(payload.data, seriesKeys, labels, { league, yAxisRange: "auto" });
}
