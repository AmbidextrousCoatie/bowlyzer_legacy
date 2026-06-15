import { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useMobileNav } from "../../context/MobileNavContext";
import {
  useAvailableLeagues,
  useAvailableRounds,
  useAvailableSeasons,
  useAvailableTeams,
  useAvailableWeeks,
} from "../../hooks/useLeague";
import { useTranslations } from "../../hooks/useTranslations";
import { seasonForUrlQuery } from "../../lib/api";
import {
  isLeagueAllSeasons,
  LEAGUE_SEASON_ALL,
  LEAGUE_SEASON_LATEST,
  leagueSeasonFilterLabel,
  resolveLeagueApiSeason,
} from "../../lib/leagueSeason";
import { GameOverview, GameTeamDetails } from "./blocks/GameBlocks";
import { LeagueOverview } from "./blocks/LeagueOverview";
import { LeagueSeasonOverview } from "./blocks/LeagueSeasonOverview";
import { Matchday } from "./blocks/Matchday";
import { SeasonLeagueStandings } from "./blocks/SeasonLeagueStandings";
import { TeamDetails } from "./blocks/TeamDetails";
import { TeamPerformance } from "./blocks/TeamPerformance";
import { LeagueFilterBar } from "./LeagueFilterBar";

export function LeagueStats() {
  const { setCompactPageChrome } = useMobileNav();
  const [searchParams, setSearchParams] = useSearchParams();
  const season = searchParams.get("season") ?? LEAGUE_SEASON_LATEST;
  const league = searchParams.get("league") ?? "";
  const week = searchParams.get("week") ?? "";
  const team = searchParams.get("team") ?? "";
  const round = searchParams.get("round") ?? "";
  const { t } = useTranslations();

  useEffect(() => {
    setCompactPageChrome(true);
    return () => setCompactPageChrome(false);
  }, [setCompactPageChrome]);

  const seasonsQuery = useAvailableSeasons();
  const seasonList = seasonsQuery.data ?? [];
  const resolvedSeason = useMemo(() => {
    if (!seasonsQuery.isSuccess) return null;
    return resolveLeagueApiSeason(season, seasonList, league);
  }, [seasonsQuery.isSuccess, season, seasonList, league]);

  const leaguesSeason = isLeagueAllSeasons(season) ? null : resolvedSeason;
  const leaguesQuery = useAvailableLeagues(leaguesSeason);
  const weeksQuery = useAvailableWeeks(resolvedSeason, league || null);
  const teamsQuery = useAvailableTeams(resolvedSeason, league || null);
  const roundsQuery = useAvailableRounds(resolvedSeason, league || null, week || null);

  function setParam(key: string, value: string, drop: string[] = []) {
    const next = new URLSearchParams(searchParams);
    if (value === "") next.delete(key);
    else if (key === "season" && (value === LEAGUE_SEASON_ALL || value === LEAGUE_SEASON_LATEST)) {
      next.set("season", value);
    }
    else next.set(key, key === "season" ? seasonForUrlQuery(value) : value);
    drop.forEach((k) => next.delete(k));
    setSearchParams(next, { replace: false });
  }

  const showSeasonStandings = !!resolvedSeason && !league && !isLeagueAllSeasons(season);
  const showLeagueOverview =
    isLeagueAllSeasons(season) && !!league && !week && !team;
  const showLeagueSeasonOverview =
    !isLeagueAllSeasons(season) && !!league && !!resolvedSeason && !week && !team;
  const showMatchday = !!resolvedSeason && !!league && !!week && !team && !round;
  const showTeamPerformance = !!league && !!resolvedSeason && !!team && !week;
  const showTeamDetails = !!resolvedSeason && !!league && !!week && !!team && !round;
  const showGameOverview = !!resolvedSeason && !!league && !!week && !!round && !team;
  const showGameTeamDetails = !!resolvedSeason && !!league && !!week && !!team && !!round;

  const seasonHeading = leagueSeasonFilterLabel(season, t);

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
            <span className="font-mono">{seasonHeading}</span>
          </span>
        </h1>
      </header>

      <LeagueFilterBar
        pageName={t("league_statistics", "Bowl-A-Lyzer")}
        pageHeading={`${t("league", "Liga")} · ${t("season", "Saison")} ${seasonHeading}`}
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
        {showLeagueOverview && <LeagueOverview league={league} />}
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
