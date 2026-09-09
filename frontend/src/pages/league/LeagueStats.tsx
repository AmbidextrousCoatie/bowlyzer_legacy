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
import { useMyClub } from "../../hooks/useMyClub";
import { useTranslations } from "../../hooks/useTranslations";
import { seasonForUrlQuery } from "../../lib/api";
import {
  isLeagueAllSeasons,
  LEAGUE_SEASON_ALL,
  LEAGUE_SEASON_LATEST,
  leagueSeasonFilterLabel,
  resolveLeagueApiSeason,
} from "../../lib/leagueSeason";
import { isLeagueRegion, leagueInRegionScope, getLeagueLevel } from "../../lib/leagueLevel";
import { parseLeagueLevelParam, parseLeagueSelectValue } from "../../lib/leagueSelect";
import { leaguesForSeason } from "../../lib/myClub";
import { normalizeUnicodeLabel, teamsForClub } from "../../lib/teamUtils";
import { GameOverview, GameTeamDetails } from "./blocks/GameBlocks";
import { LeagueOverview } from "./blocks/LeagueOverview";
import { LeagueSeasonOverview } from "./blocks/LeagueSeasonOverview";
import { Matchday } from "./blocks/Matchday";
import { SeasonLeagueStandings } from "./blocks/SeasonLeagueStandings";
import { SeasonSpielplan } from "./blocks/SeasonSpielplan";
import { TeamDetails } from "./blocks/TeamDetails";
import { TeamPerformance } from "./blocks/TeamPerformance";
import { LeagueFilterBar } from "./LeagueFilterBar";
import { ContextualHint } from "../../components/ContextualHint";
import { TopicPageHeader } from "../../components/TopicPageHeader";
import { Link } from "react-router-dom";

export function LeagueStats() {
  const { setCompactPageChrome } = useMobileNav();
  const [searchParams, setSearchParams] = useSearchParams();
  const season = searchParams.get("season") ?? LEAGUE_SEASON_LATEST;
  const league = searchParams.get("league") ?? "";
  const division = searchParams.get("division") ?? "";
  const level = parseLeagueLevelParam(searchParams.get("level") ?? "");
  const week = searchParams.get("week") ?? "";
  const team = searchParams.get("team") ?? "";
  const round = searchParams.get("round") ?? "";
  const { t } = useTranslations();
  const { active: myClubActive, resolvedClub, participation, participationLoading } = useMyClub();

  useEffect(() => {
    setCompactPageChrome(true);
    return () => setCompactPageChrome(false);
  }, [setCompactPageChrome]);

  const seasonsQuery = useAvailableSeasons();
  const seasonList = useMemo(() => {
    const all = seasonsQuery.data ?? [];
    if (!myClubActive || !participation) return all;
    const allowed = new Set(participation.seasons.map(normalizeUnicodeLabel));
    return all.filter((s) => allowed.has(normalizeUnicodeLabel(s)));
  }, [seasonsQuery.data, myClubActive, participation]);

  const resolvedSeason = useMemo(() => {
    if (!seasonsQuery.isSuccess) return null;
    return resolveLeagueApiSeason(season, seasonList, league);
  }, [seasonsQuery.isSuccess, season, seasonList, league]);

  const leaguesSeason = isLeagueAllSeasons(season) ? null : resolvedSeason;
  const leaguesQuery = useAvailableLeagues(leaguesSeason);
  const weeksQuery = useAvailableWeeks(resolvedSeason, league || null);
  const teamsQuery = useAvailableTeams(resolvedSeason, league || null);
  const roundsQuery = useAvailableRounds(resolvedSeason, league || null, week || null);

  const filteredLeagues = useMemo(() => {
    const all = leaguesQuery.data ?? [];
    if (!myClubActive || !participation) return all;
    const allowedList = leaguesForSeason(
      participation,
      isLeagueAllSeasons(season) ? null : resolvedSeason,
    );
    if (!allowedList) return all;
    const allowed = new Set(allowedList.map(normalizeUnicodeLabel));
    return all.filter(
      (l) =>
        allowed.has(normalizeUnicodeLabel(l.value)) ||
        allowed.has(normalizeUnicodeLabel(l.short_name)),
    );
  }, [leaguesQuery.data, myClubActive, participation, season, resolvedSeason]);

  const region = isLeagueRegion(division) ? division : "";
  const scopedLeagues = useMemo(() => {
    let list = filteredLeagues;
    if (region) {
      list = list.filter((item) => leagueInRegionScope(item.value, region));
    }
    if (level != null) {
      list = list.filter((item) => getLeagueLevel(item.value) === level);
    }
    return list;
  }, [filteredLeagues, region, level]);

  const filteredTeams = useMemo(() => {
    const all = teamsQuery.data ?? [];
    if (!myClubActive || !resolvedClub) return all;
    return teamsForClub(all, resolvedClub);
  }, [teamsQuery.data, myClubActive, resolvedClub]);

  // Drop stale liga filters that fall outside the club's participation.
  useEffect(() => {
    if (!myClubActive || participationLoading || !participation) return;
    const next = new URLSearchParams(searchParams);
    let changed = false;

    if (
      season &&
      season !== LEAGUE_SEASON_LATEST &&
      season !== LEAGUE_SEASON_ALL &&
      !participation.seasons.some((s) => normalizeUnicodeLabel(s) === normalizeUnicodeLabel(season))
    ) {
      next.set("season", LEAGUE_SEASON_LATEST);
      next.delete("league");
      next.delete("week");
      next.delete("team");
      next.delete("round");
      changed = true;
    } else if (league) {
      const allowedList = leaguesForSeason(
        participation,
        isLeagueAllSeasons(season) ? null : resolvedSeason,
      );
      const allowed = new Set((allowedList ?? []).map(normalizeUnicodeLabel));
      if (!allowed.has(normalizeUnicodeLabel(league))) {
        next.delete("league");
        next.delete("week");
        next.delete("team");
        next.delete("round");
        changed = true;
      }
    } else {
      const allowedList = leaguesForSeason(
        participation,
        isLeagueAllSeasons(season) ? null : resolvedSeason,
      );
      if (allowedList) {
        if (region && !allowedList.some((id) => leagueInRegionScope(id, region))) {
          next.delete("division");
          changed = true;
        }
        const divisionAfter = next.get("division") ?? "";
        const regionAfter = isLeagueRegion(divisionAfter) ? divisionAfter : "";
        if (
          level != null &&
          !allowedList.some((id) => {
            if (getLeagueLevel(id) !== level) return false;
            return !regionAfter || leagueInRegionScope(id, regionAfter);
          })
        ) {
          next.delete("level");
          changed = true;
        }
      }
    }

    if (team && resolvedClub) {
      const clubTeams = teamsForClub(teamsQuery.data ?? [], resolvedClub);
      if (
        teamsQuery.isSuccess &&
        clubTeams.length > 0 &&
        !clubTeams.some((tm) => normalizeUnicodeLabel(tm) === normalizeUnicodeLabel(team))
      ) {
        next.delete("team");
        next.delete("round");
        changed = true;
      }
    }

    if (changed) setSearchParams(next, { replace: true });
  }, [
    myClubActive,
    participationLoading,
    participation,
    season,
    league,
    region,
    level,
    team,
    resolvedSeason,
    resolvedClub,
    teamsQuery.isSuccess,
    teamsQuery.data,
    searchParams,
    setSearchParams,
  ]);

  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    let changed = false;
    const rawLevel = searchParams.get("level");

    if (league) {
      if (division) {
        next.delete("division");
        changed = true;
      }
      if (rawLevel) {
        next.delete("level");
        changed = true;
      }
    } else {
      if (division && !isLeagueRegion(division)) {
        next.delete("division");
        changed = true;
      }
      if (rawLevel && level == null) {
        next.delete("level");
        changed = true;
      }
      if (
        level != null &&
        filteredLeagues.length > 0 &&
        !filteredLeagues.some((item) => {
          if (getLeagueLevel(item.value) !== level) return false;
          return !region || leagueInRegionScope(item.value, region);
        })
      ) {
        next.delete("level");
        changed = true;
      }
    }

    if (changed) setSearchParams(next, { replace: true });
  }, [division, league, level, region, filteredLeagues, searchParams, setSearchParams]);

  function setParam(key: string, value: string, drop: string[] = []) {
    const next = new URLSearchParams(searchParams);
    if (value === "") next.delete(key);
    else if (key === "season" && (value === LEAGUE_SEASON_ALL || value === LEAGUE_SEASON_LATEST)) {
      next.set("season", value);
    } else next.set(key, key === "season" ? seasonForUrlQuery(value) : value);
    drop.forEach((k) => next.delete(k));
    setSearchParams(next, { replace: false });
  }

  function onLeagueSelect(value: string) {
    const parsed = parseLeagueSelectValue(value);
    const next = new URLSearchParams(searchParams);
    next.delete("league");
    for (const key of ["week", "team", "round"]) next.delete(key);
    if (parsed.league) {
      next.set("league", parsed.league);
      next.delete("division");
      next.delete("level");
    } else if (parsed.division) {
      next.set("division", parsed.division);
      next.delete("level");
    } else if (parsed.level != null) {
      next.set("level", String(parsed.level));
    } else {
      next.delete("division");
      next.delete("level");
    }
    setSearchParams(next, { replace: false });
  }

  const showSeasonStandings = !!resolvedSeason && !league && !isLeagueAllSeasons(season);
  const showLeagueOverview = isLeagueAllSeasons(season) && !!league && !week && !team;
  const showLeagueSeasonOverview =
    !isLeagueAllSeasons(season) && !!league && !!resolvedSeason && !week && !team;
  const showMatchday = !!resolvedSeason && !!league && !!week && !team && !round;
  const showTeamPerformance = !!league && !!resolvedSeason && !!team && !week;
  const showTeamDetails = !!resolvedSeason && !!league && !!week && !!team && !round;
  const showGameOverview = !!resolvedSeason && !!league && !!week && !!round && !team;
  const showGameTeamDetails = !!resolvedSeason && !!league && !!week && !!team && !!round;

  const seasonHeading = leagueSeasonFilterLabel(season, t);
  const allowedLeaguesForStandings = useMemo(() => {
    if (league) return null;
    if (region || level != null) return scopedLeagues.map((item) => item.value);
    if (!myClubActive || !participation || !resolvedSeason) return null;
    return leaguesForSeason(participation, resolvedSeason);
  }, [league, region, level, scopedLeagues, myClubActive, participation, resolvedSeason]);

  return (
    <div className="mx-auto max-w-[1280px] px-4 pt-8 pb-24 max-lg:landscape:pt-2 lg:px-8 lg:pt-12">
      <TopicPageHeader
        topic="league"
        eyebrow={t("league_statistics", "Bowl-A-Lyzer")}
        hideOnLandscape
        title={
          <>
            {t("league", "Liga")} ·{" "}
            <span className="text-muted font-normal">
              {t("season", "Saison")} <span className="font-mono">{seasonHeading}</span>
            </span>
          </>
        }
        description={t(
          "ui.league.page_desc",
          "Ligatabellen und Spieltag-Ergebnisse — wähle Saison, Liga und Spieltag in der Filterleiste.",
        )}
      />

      <ContextualHint hintId="league-filter-cascade" className="mb-6 max-lg:landscape:hidden">
        <span>
          {t(
            "ui.league.filter_hint",
            "So navigierst du: Saison → Liga → Spieltag → Mannschaft. Die Tabelle zeigt die Platzierungen wie in der gewohnten Ergebnisliste.",
          )}{" "}
          <Link to="/glossar" className="text-accent hover:underline">
            {t("ui.nav.glossary", "Glossar")}
          </Link>
        </span>
      </ContextualHint>

      <LeagueFilterBar
        pageName={t("league_statistics", "Bowl-A-Lyzer")}
        pageHeading={`${t("league", "Liga")} · ${t("season", "Saison")} ${seasonHeading}`}
        season={season}
        seasons={seasonList}
        seasonsLoading={seasonsQuery.isPending || (myClubActive && participationLoading)}
        league={league}
        division={region}
        level={level}
        leagues={filteredLeagues}
        leaguesLoading={leaguesQuery.isPending || (myClubActive && participationLoading)}
        week={week}
        weeks={weeksQuery.data ?? []}
        weeksLoading={weeksQuery.isPending}
        team={team}
        teams={filteredTeams}
        teamsLoading={teamsQuery.isPending}
        round={round}
        rounds={roundsQuery.data ?? []}
        roundsLoading={roundsQuery.isPending}
        onSeasonChange={(v) => setParam("season", v, ["league", "week", "team", "round"])}
        onLeagueChange={onLeagueSelect}
        onWeekChange={(v) => setParam("week", v, ["round"])}
        onTeamChange={(v) => setParam("team", v, ["round"])}
        onRoundChange={(v) => setParam("round", v)}
        t={t}
      />

      <div className="mt-6 space-y-12 lg:mt-10">
        {showSeasonStandings && resolvedSeason && (
          <>
            <SeasonSpielplan
              season={resolvedSeason}
              leagues={scopedLeagues}
              leaguesLoading={leaguesQuery.isPending || (myClubActive && participationLoading)}
            />
            <SeasonLeagueStandings
              season={resolvedSeason}
              allowedLeagues={allowedLeaguesForStandings}
              levelFilter={level}
            />
          </>
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
