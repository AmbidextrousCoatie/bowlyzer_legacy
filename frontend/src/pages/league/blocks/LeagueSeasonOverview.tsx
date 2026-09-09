import { useCallback, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { seedTeamColorsFromTablePayload } from "../../../lib/color-utils";
import {
  buildWeekLabels,
  lineChartOption,
  scatterMultiAxisOption,
} from "../../../lib/charts/options";
import { DataTable } from "../../../lib/datatable/DataTable";
import type { DataTableHandle } from "../../../lib/datatable/createDataTable";
import type { DataTableOptions, TableData } from "../../../lib/datatable/types";
import { useAppLink } from "../../../hooks/useAppLink";
import { useLigaTableNavigation } from "../../../hooks/useLigaTableNavigation";
import {
  useIndividualAverages,
  useLeagueHistory,
  useSeasonTimetable,
  useTeamPoints,
  useTeamPositions,
  useTeamVsTeamComparison,
} from "../../../hooks/useLeague";
import { useTranslations } from "../../../hooks/useTranslations";
import { formatTimetableTable } from "../../../lib/seasonSpielplan";
import { rankedTeamTableOptions, teamVsTeamTableOptions } from "../leagueTableOptions";
import { ChartFrame, DataTableSection, Section } from "./leagueBlockUi";
import { TeamVsTeamMatrix } from "./TeamVsTeamMatrix";

type Props = {
  season: string;
  league: string;
};

/**
 * Renders when both season and league are selected (without week or team).
 * Sectioned layout: standings → timetable + position-progress chart →
 * weekly-points + cumulative-points charts → team-vs-team matrix → individual
 * averages.
 */
export function LeagueSeasonOverview({ season, league }: Props) {
  const { t, language } = useTranslations();
  const weekLabel = t("week", "Spieltag");
  const standingsNav = useLigaTableNavigation(season, league);
  const teamVsTeamNav = useLigaTableNavigation(season, league, { kind: "teamVsTeam" });
  const averagesNav = useLigaTableNavigation(season, league, { kind: "averages" });

  const standings = useLeagueHistory(season, league);
  const timetable = useSeasonTimetable(season, league);
  const timetableTable = useMemo(
    () => formatTimetableTable(timetable.data, language === "en" ? "en" : "de"),
    [timetable.data, language],
  );
  const teamPositions = useTeamPositions(season, league);
  const teamPoints = useTeamPoints(season, league);
  const teamVsTeam = useTeamVsTeamComparison(season, league);
  const individualAverages = useIndividualAverages(season, league);

  const positionsOption = useMemo(() => {
    if (!teamPositions.data?.data) return null;
    const order =
      teamPositions.data.sorted_by_best ??
      teamPositions.data.sorted_by_total ??
      Object.keys(teamPositions.data.data);
    return lineChartOption(
      teamPositions.data.data,
      order,
      buildWeekLabels(teamPositions.data.data, weekLabel),
      { invertYAxis: true, yAxisRange: "exact", league },
    );
  }, [teamPositions.data, weekLabel, league]);

  const weeklyPointsOption = useMemo(() => {
    if (!teamPoints.data?.data) return null;
    const order = teamPoints.data.sorted_by_total ?? Object.keys(teamPoints.data.data);
    return scatterMultiAxisOption(
      teamPoints.data.data,
      order,
      buildWeekLabels(teamPoints.data.data, weekLabel),
      { tooltipValueLabel: t("points", "Punkte"), league },
    );
  }, [teamPoints.data, weekLabel, t, league]);

  useEffect(() => {
    if (standings.data) seedTeamColorsFromTablePayload(standings.data, league);
  }, [standings.data, league]);

  const cumulativePointsOption = useMemo(() => {
    const accumulated = teamPoints.data?.data_accumulated;
    if (!accumulated) return null;
    const order = teamPoints.data?.sorted_by_total ?? Object.keys(accumulated);
    return lineChartOption(accumulated, order, buildWeekLabels(accumulated, weekLabel), {
      invertYAxis: false,
      yAxisRange: "auto",
      league,
    });
  }, [teamPoints.data, weekLabel, league]);

  const standingsTableOptions = useMemo<DataTableOptions>(
    () => ({
      ...rankedTeamTableOptions,
      seedTeamColorsFromTable: true,
      disableTeamColorUpdate: true,
      teamColorLeague: league,
      leagueNavigation: standingsNav,
    }),
    [league, standingsNav],
  );

  const basicTableOptions = useMemo<DataTableOptions>(
    () => ({
      disablePositionCircle: true,
      enableSpecialRowStyling: true,
      tooltips: true,
    }),
    [],
  );

  const teamVsTeamOptions = useMemo(
    () => ({
      ...teamVsTeamTableOptions,
      teamColorLeague: league,
      leagueNavigation: teamVsTeamNav,
    }),
    [league, teamVsTeamNav],
  );

  const averagesTableOptions = useMemo<DataTableOptions>(
    () => ({
      ...basicTableOptions,
      leagueNavigation: averagesNav,
    }),
    [basicTableOptions, averagesNav],
  );

  return (
    <div className="space-y-12">
      {/* 1 · Standings table */}
      <Section
        eyebrow={t("league_standings", "Tabelle")}
        title={t("league_standings_title", `${league} · ${season}`)}
      >
        <DataTableSection query={standings} options={standingsTableOptions} />
      </Section>

      {/* 2 · Timetable + Position chart */}
      <div className="grid grid-cols-1 gap-12 lg:grid-cols-2">
        <Section eyebrow={t("season_timetable", "Spielplan")} title={t("schedule", "Termine")}>
          <TermineTable
            query={timetable}
            table={timetableTable}
            season={season}
            league={league}
            options={basicTableOptions}
          />
        </Section>
        <Section
          eyebrow={t("position_in_season_progress", "Tabellenposition")}
          title={t("over_time", "Saisonverlauf")}
        >
          <ChartFrame
            isPending={teamPositions.isPending}
            isError={teamPositions.isError}
            errorMessage={teamPositions.error?.message}
            option={positionsOption}
          />
        </Section>
      </div>

      {/* 3 · Weekly + Cumulative points charts */}
      <div className="grid grid-cols-1 gap-12 lg:grid-cols-2">
        <Section
          eyebrow={t("points_per_match_day", "Punkte pro Spieltag")}
          title={t("weekly_points", "Wochenpunkte")}
        >
          <ChartFrame
            isPending={teamPoints.isPending}
            isError={teamPoints.isError}
            errorMessage={teamPoints.error?.message}
            option={weeklyPointsOption}
          />
        </Section>
        <Section
          eyebrow={t("points_in_season_progress", "Punkte kumuliert")}
          title={t("cumulative_points", "Saisonverlauf")}
        >
          <ChartFrame
            isPending={teamPoints.isPending}
            isError={teamPoints.isError}
            errorMessage={teamPoints.error?.message}
            option={cumulativePointsOption}
          />
        </Section>
      </div>

      {/* 4 · Team vs Team comparison matrix */}
      <Section
        eyebrow={t("team_vs_team_comparison", "Vergleichsmatrix")}
        title={t("team_vs_team", "Mannschaft vs. Mannschaft")}
      >
        <TeamVsTeamMatrix query={teamVsTeam} options={teamVsTeamOptions} />
      </Section>

      {/* 5 · Individual averages */}
      <Section
        eyebrow={t("individual_averages", "Einzelschnitte")}
        title={t("best_individual_averages", "Beste Spieler-Schnitte")}
      >
        <DataTableSection query={individualAverages} options={averagesTableOptions} />
      </Section>
    </div>
  );
}

function TermineTable({
  query,
  table,
  season,
  league,
  options,
}: {
  query: { isPending: boolean; isError: boolean; error: Error | null };
  table: TableData | undefined;
  season: string;
  league: string;
  options: DataTableOptions;
}) {
  const navigate = useNavigate();
  const linkTo = useAppLink();
  const onReady = useCallback(
    (handle: DataTableHandle) => {
      handle.tabulator.on("cellClick", (_event, cell) => {
        const row = cell.getData() as { week?: number | string };
        const week = row.week;
        if (week == null || week === "") return;
        void navigate(linkTo("/liga", { season, league, week }));
      });
    },
    [league, linkTo, navigate, season],
  );

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
  if (!table?.columns || !table?.data?.length) {
    return (
      <div className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
        Keine Daten vorhanden.
      </div>
    );
  }
  return <DataTable data={table} options={options} onReady={onReady} className="cursor-pointer" />;
}
