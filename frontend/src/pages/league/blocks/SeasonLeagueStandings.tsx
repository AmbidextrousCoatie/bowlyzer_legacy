import { useCallback, useEffect, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { DataTable } from "../../../lib/datatable/DataTable";
import { buildLeagueNavPath } from "../../../lib/leagueNavigation";
import { type HonorScores, useSeasonLeagueStandings } from "../../../hooks/useLeague";
import { useTranslations } from "../../../hooks/useTranslations";
import { seedTeamColorsFromTablePayload } from "../../../lib/color-utils";
import { rankedTeamTableOptions } from "../leagueTableOptions";
import { HonorScoresPanel } from "./HonorScoresPanel";

type Props = {
  season: string;
};

/**
 * Visible when a season is selected but no league is. Shows current standings
 * for every league in that season, plus honor scores per league.
 *
 * Each league gets its own team-color cycle starting from palette index 0 so
 * colors don't clash across leagues. The legacy block does this by mutating
 * `teamColorMap` directly before rendering each table; we mirror that.
 */
export function SeasonLeagueStandings({ season }: Props) {
  const { t } = useTranslations();
  const { data, isPending, isError, error } = useSeasonLeagueStandings(season);

  // Seed each league in order (legacy renders tables sequentially) so identical team
  // names in different leagues get independent palette cycles.
  useEffect(() => {
    if (!data?.leagues?.length) return;
    for (const leagueData of data.leagues) {
      if (leagueData.standings?.data?.length) {
        seedTeamColorsFromTablePayload(leagueData.standings, leagueData.league);
      }
    }
  }, [data]);

  if (isPending) {
    return <SectionSkeleton label={t("status.loading", "Lade Daten…")} />;
  }
  if (isError) {
    return (
      <SectionError
        message={error instanceof Error ? error.message : t("error_generic", "Fehler beim Laden")}
      />
    );
  }
  if (!data || !data.leagues || data.leagues.length === 0) {
    return (
      <SectionEmpty message={t("no_data_available_for", `Keine Daten für Saison ${season}`)} />
    );
  }

  return (
    <>
      {data.leagues.map((leagueData) => (
        <LeagueSection
          key={leagueData.league}
          season={season}
          league={leagueData.league}
          leagueLong={leagueData.league_long}
          week={leagueData.week}
          standings={leagueData.standings}
          honorScores={leagueData.honor_scores}
          t={t}
        />
      ))}
    </>
  );
}

function LeagueSection({
  season,
  league,
  leagueLong,
  week,
  standings,
  honorScores,
  t,
}: {
  season: string;
  league: string;
  leagueLong?: string;
  week: number | string;
  standings: import("../../../lib/datatable/types").TableData;
  honorScores?: HonorScores;
  t: (key: string, fallback?: string) => string;
}) {
  const navigate = useNavigate();
  const weekPath = buildLeagueNavPath(
    { view: "league-week" },
    { season, league, defaultWeek: week },
  );
  const onNavigate = useCallback((path: string) => navigate(path), [navigate]);
  const tableOptions = useMemo(
    () => ({
      ...rankedTeamTableOptions,
      disableTeamColorUpdate: true,
      teamColorLeague: league,
      leagueNavigation: {
        season,
        league,
        defaultWeek: week,
        onNavigate,
      },
    }),
    [season, league, week, onNavigate],
  );

  return (
    <section>
      <div className="mb-4">
        <p className="text-label uppercase text-muted mb-1.5">{t("league", "Liga")}</p>
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="text-h2">
            <Link
              to={weekPath}
              className="text-foreground hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              {leagueLong ?? league}
            </Link>
          </h2>
          <p className="text-small font-mono text-muted">
            {t("match_day_label", "Spieltag")}{" "}
            <span className="font-semibold text-foreground">{week}</span>
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[2fr_1fr]">
        <div>
          <DataTable data={standings} options={tableOptions} />
        </div>
        <HonorScoresPanel
          honorScores={honorScores}
          t={t}
          navigation={{ season, league, defaultWeek: week }}
        />
      </div>
    </section>
  );
}

function SectionSkeleton({ label }: { label: string }) {
  return (
    <section>
      <div className="mb-4">
        <div className="h-3 w-24 rounded-xs bg-surface-subtle" />
        <div className="mt-2 h-6 w-64 rounded-xs bg-surface-subtle" />
      </div>
      <div className="h-64 rounded-sm border border-border bg-surface-subtle" />
      <span className="sr-only">{label}</span>
    </section>
  );
}

function SectionEmpty({ message }: { message: string }) {
  return (
    <section className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
      {message}
    </section>
  );
}

function SectionError({ message }: { message: string }) {
  return (
    <section className="rounded-sm border border-danger-fg/40 bg-surface p-6 text-small text-danger-fg">
      {message}
    </section>
  );
}
