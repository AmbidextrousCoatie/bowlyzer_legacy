import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useMobileNav } from "../../context/MobileNavContext";
import {
  pickLatestSeason,
  useAvailableLeagues,
  useAvailableRounds,
  useAvailableSeasons,
  useAvailableTeams,
  useAvailableWeeks,
} from "../../hooks/useLeague";
import { useTranslations } from "../../hooks/useTranslations";
import { GameOverview, GameTeamDetails } from "./blocks/GameBlocks";
import { LeagueSeasonOverview } from "./blocks/LeagueSeasonOverview";
import { Matchday } from "./blocks/Matchday";
import { SeasonLeagueStandings } from "./blocks/SeasonLeagueStandings";
import { TeamDetails } from "./blocks/TeamDetails";
import { TeamPerformance } from "./blocks/TeamPerformance";
import { LeagueFilterBar } from "./LeagueFilterBar";

export function LeagueStats() {
  const { setLeagueCompactChrome } = useMobileNav();
  const [searchParams, setSearchParams] = useSearchParams();
  const season = searchParams.get("season") ?? "latest";
  const league = searchParams.get("league") ?? "";
  const week = searchParams.get("week") ?? "";
  const team = searchParams.get("team") ?? "";
  const round = searchParams.get("round") ?? "";
  const { t } = useTranslations();

  useEffect(() => {
    setLeagueCompactChrome(true);
    return () => setLeagueCompactChrome(false);
  }, [setLeagueCompactChrome]);

  const seasonsQuery = useAvailableSeasons();
  const seasonList = seasonsQuery.data ?? [];
  const resolvedSeason =
    season === "latest"
      ? seasonsQuery.isSuccess
        ? pickLatestSeason(seasonList)
        : null
      : season;

  useEffect(() => {
    if (!seasonsQuery.isSuccess) return;
    if (season !== "latest" || seasonList.length === 0) return;
    const latest = pickLatestSeason(seasonList);
    if (!latest) return;
    const next = new URLSearchParams(searchParams);
    next.set("season", latest);
    setSearchParams(next, { replace: true });
  }, [seasonsQuery.isSuccess, seasonsQuery.data, season, searchParams, setSearchParams]);

  const leaguesQuery = useAvailableLeagues(resolvedSeason);
  const weeksQuery = useAvailableWeeks(resolvedSeason, league || null);
  const teamsQuery = useAvailableTeams(resolvedSeason, league || null);
  const roundsQuery = useAvailableRounds(resolvedSeason, league || null, week || null);

  function setParam(key: string, value: string, drop: string[] = []) {
    const next = new URLSearchParams(searchParams);
    if (value === "") next.delete(key);
    else next.set(key, value);
    drop.forEach((k) => next.delete(k));
    setSearchParams(next, { replace: false });
  }

  const showSeasonStandings = !!resolvedSeason && !league;
  const showLeagueSeasonOverview = !!league && !!resolvedSeason && !week && !team;
  const showMatchday = !!resolvedSeason && !!league && !!week && !team && !round;
  const showTeamPerformance = !!league && !!resolvedSeason && !!team && !week;
  const showTeamDetails = !!resolvedSeason && !!league && !!week && !!team && !round;
  const showGameOverview = !!resolvedSeason && !!league && !!week && !!round && !team;
  const showGameTeamDetails = !!resolvedSeason && !!league && !!week && !!team && !!round;

  return (
    <div className="mx-auto max-w-[1280px] px-4 pt-8 pb-24 max-lg:landscape:pt-2 lg:px-8 lg:pt-12">
      <header className="mb-6 max-lg:landscape:hidden lg:mb-8">
        <p className="text-label uppercase text-muted mb-2">
          {t("league_statistics", "Bowl-A-Lyzer")}
        </p>
        <h1 className="text-h1">
          {t("league", "Liga")} ·{" "}
          <span className="text-muted font-normal">
            {t("season", "Saison")}{" "}
            <span className="font-mono">{seasonDisplay(resolvedSeason ?? season)}</span>
          </span>
        </h1>
      </header>

      <LeagueFilterBar
        pageName={t("league_statistics", "Bowl-A-Lyzer")}
        pageHeading={buildLeaguePageHeading(t, resolvedSeason ?? season)}
        season={season}
        seasons={seasonsQuery.data ?? []}
        seasonsLoading={seasonsQuery.isPending}
        league={league}
        leagues={leaguesQuery.data ?? []}
        leaguesLoading={leaguesQuery.isPending}
        week={week}
        weeks={weeksQuery.data ?? []}
        weeksLoading={weeksQuery.isPending}
        team={team}
        teams={teamsQuery.data ?? []}
        teamsLoading={teamsQuery.isPending}
        round={round}
        rounds={roundsQuery.data ?? []}
        roundsLoading={roundsQuery.isPending}
        onSeasonChange={(v) => setParam("season", v, ["league", "week", "team", "round"])}
        onLeagueChange={(v) => setParam("league", v, ["week", "team", "round"])}
        onWeekChange={(v) => setParam("week", v, ["round"])}
        onTeamChange={(v) => setParam("team", v, ["round"])}
        onRoundChange={(v) => setParam("round", v)}
        t={t}
      />

      <div className="mt-6 space-y-12 lg:mt-10">
        {showSeasonStandings && resolvedSeason && (
          <SeasonLeagueStandings season={resolvedSeason} />
        )}
        {showLeagueSeasonOverview && resolvedSeason && (
          <LeagueSeasonOverview season={resolvedSeason} league={league} />
        )}
        {showMatchday && resolvedSeason && (
          <Matchday season={resolvedSeason} league={league} week={week} />
        )}
        {showTeamPerformance && resolvedSeason && (
          <TeamPerformance season={resolvedSeason} league={league} team={team} />
        )}
        {showTeamDetails && resolvedSeason && (
          <TeamDetails season={resolvedSeason} league={league} week={week} team={team} />
        )}
        {showGameOverview && resolvedSeason && (
          <GameOverview season={resolvedSeason} league={league} week={week} round={round} />
        )}
        {showGameTeamDetails && resolvedSeason && (
          <GameTeamDetails
            season={resolvedSeason}
            league={league}
            week={week}
            team={team}
            round={round}
          />
        )}
      </div>
    </div>
  );
}

function seasonDisplay(season: string): string {
  return season === "latest" ? "—" : season;
}

function buildLeaguePageHeading(
  t: (key: string, fallback?: string) => string,
  season: string,
): string {
  return `${t("league", "Liga")} · ${t("season", "Saison")} ${seasonDisplay(season)}`;
}
