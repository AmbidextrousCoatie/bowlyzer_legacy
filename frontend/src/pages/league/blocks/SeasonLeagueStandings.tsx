import { useCallback, useEffect, useMemo } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { DataTable } from "../../../lib/datatable/DataTable";
import { getLeagueLevel, getLeagueLevelLongLabel } from "../../../lib/leagueLevel";
import { buildLeagueNavPath } from "../../../lib/leagueNavigation";
import { type HonorScores, useSeasonLeagueStandings } from "../../../hooks/useLeague";
import { useTranslations } from "../../../hooks/useTranslations";
import { seedTeamColorsFromTablePayload } from "../../../lib/color-utils";
import { rankedTeamTableOptions } from "../leagueTableOptions";
import { HonorScoresPanel } from "./HonorScoresPanel";

type Props = {
  season: string;
  /** When set (Mein Club / region / level), only these league short names are shown. */
  allowedLeagues?: string[] | null;
  /** Currently selected league-level filter, if any. */
  levelFilter?: number | null;
};

/**
 * Visible when a season is selected but no league is. Shows current standings
 * for every league in that season, plus honor scores per league.
 *
 * Each league gets its own team-color cycle starting from palette index 0 so
 * colors don't clash across leagues. The legacy block does this by mutating
 * `teamColorMap` directly before rendering each table; we mirror that.
 */
export function SeasonLeagueStandings({ season, allowedLeagues, levelFilter = null }: Props) {
  const { t } = useTranslations();
  const [searchParams] = useSearchParams();
  const { data, isPending, isError, error } = useSeasonLeagueStandings(season);

  const leagues = useMemo(() => {
    const all = data?.leagues ?? [];
    const filtered = (() => {
      if (allowedLeagues == null) return all;
      const allowed = new Set(allowedLeagues.map((l) => l.trim().normalize("NFC")));
      return all.filter((row) =>
        allowed.has(
          String(row.league ?? "")
            .trim()
            .normalize("NFC"),
        ),
      );
    })();
    return [...filtered].sort((a, b) => {
      const delta = getLeagueLevel(a.league) - getLeagueLevel(b.league);
      if (delta !== 0) return delta;
      return String(a.league).localeCompare(String(b.league), "de");
    });
  }, [data?.leagues, allowedLeagues]);

  const groups = useMemo(() => {
    const byLevel: { level: number; label: string; leagues: typeof leagues }[] = [];
    for (const row of leagues) {
      const rowLevel = getLeagueLevel(row.league);
      const last = byLevel[byLevel.length - 1];
      if (last && last.level === rowLevel) {
        last.leagues.push(row);
      } else {
        byLevel.push({
          level: rowLevel,
          label: getLeagueLevelLongLabel(rowLevel),
          leagues: [row],
        });
      }
    }
    return byLevel;
  }, [leagues]);

  const levelHref = useCallback(
    (rowLevel: number) => {
      const next = new URLSearchParams(searchParams);
      next.delete("league");
      next.delete("week");
      next.delete("team");
      next.delete("round");
      next.set("level", String(rowLevel));
      return `/liga?${next.toString()}`;
    },
    [searchParams],
  );

  // Seed each league in order (legacy renders tables sequentially) so identical team
  // names in different leagues get independent palette cycles.
  useEffect(() => {
    if (!leagues.length) return;
    for (const leagueData of leagues) {
      if (leagueData.standings?.data?.length) {
        seedTeamColorsFromTablePayload(leagueData.standings, leagueData.league);
      }
    }
  }, [leagues]);

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
  if (!data || leagues.length === 0) {
    return (
      <SectionEmpty message={t("no_data_available_for", `Keine Daten für Saison ${season}`)} />
    );
  }

  return (
    <div className="space-y-16">
      {groups.map((group) => {
        const active = levelFilter != null && levelFilter === group.level;
        return (
          <div key={group.level} className="space-y-12">
            <LevelGroupHeading
              label={group.label}
              href={active ? null : levelHref(group.level)}
              t={t}
            />
            {group.leagues.map((leagueData) => (
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
          </div>
        );
      })}
    </div>
  );
}

function LevelGroupHeading({
  label,
  href,
  t,
}: {
  label: string;
  href: string | null;
  t: (key: string, fallback?: string) => string;
}) {
  const title = href ? (
    <Link
      to={href}
      aria-label={t("ui.league.filter_level", "Alle {name}-Ligen anzeigen").replace("{name}", label)}
      className="text-foreground hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      {label}
    </Link>
  ) : (
    label
  );
  return (
    <div className="border-b border-border pb-2">
      <h2 className="text-h2">{title}</h2>
    </div>
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
  const [searchParams] = useSearchParams();
  const sourceQuery = searchParams.toString();
  const weekPath = buildLeagueNavPath(
    { view: "league-week" },
    { season, league, defaultWeek: week, sourceQuery },
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
        sourceQuery,
        onNavigate,
      },
    }),
    [season, league, week, sourceQuery, onNavigate],
  );

  return (
    <section>
      <div className="mb-4">
        <div className="flex items-baseline justify-between gap-4">
          <h3 className="text-h3">
            <Link
              to={weekPath}
              className="text-foreground hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              {leagueLong ?? league}
            </Link>
          </h3>
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
          navigation={{ season, league, defaultWeek: week, sourceQuery }}
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
