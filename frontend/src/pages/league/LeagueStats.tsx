import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
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

export function LeagueStats() {
  const [searchParams, setSearchParams] = useSearchParams();
  const season = searchParams.get("season") ?? "latest";
  const league = searchParams.get("league") ?? "";
  const week = searchParams.get("week") ?? "";
  const team = searchParams.get("team") ?? "";
  const round = searchParams.get("round") ?? "";
  const { t } = useTranslations();

  const seasonsQuery = useAvailableSeasons();
  const seasonList = seasonsQuery.data ?? [];
  const resolvedSeason =
    season === "latest"
      ? seasonsQuery.isSuccess
        ? pickLatestSeason(seasonList)
        : null
      : season;

  // Resolve "latest" (default on /liga) to a concrete season in the URL.
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

  // Visibility precedence (matches legacy block shouldRender contracts).
  const showSeasonStandings = !!resolvedSeason && !league;
  const showLeagueSeasonOverview = !!league && !!resolvedSeason && !week && !team;
  const showMatchday = !!resolvedSeason && !!league && !!week && !team && !round;
  const showTeamPerformance = !!league && !!resolvedSeason && !!team && !week;
  const showTeamDetails = !!resolvedSeason && !!league && !!week && !!team && !round;
  const showGameOverview = !!resolvedSeason && !!league && !!week && !!round && !team;
  const showGameTeamDetails = !!resolvedSeason && !!league && !!week && !!team && !!round;

  return (
    <div className="mx-auto max-w-[1280px] px-8 pt-12 pb-24">
      <header className="mb-8">
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

      <FilterRail
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

      <div className="mt-10 space-y-12">
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

type FilterRailProps = {
  season: string;
  seasons: string[];
  seasonsLoading: boolean;
  league: string;
  leagues: { short_name: string; long_name: string; value: string }[];
  leaguesLoading: boolean;
  week: string;
  weeks: number[];
  weeksLoading: boolean;
  team: string;
  teams: string[];
  teamsLoading: boolean;
  round: string;
  rounds: number[];
  roundsLoading: boolean;
  onSeasonChange: (v: string) => void;
  onLeagueChange: (v: string) => void;
  onWeekChange: (v: string) => void;
  onTeamChange: (v: string) => void;
  onRoundChange: (v: string) => void;
  t: (key: string, fallback?: string) => string;
};

function FilterRail(props: FilterRailProps) {
  const { t } = props;
  const showWeek = !!props.league;
  const showTeam = !!props.league;
  const showRound = !!props.week;

  return (
    <div className="sticky top-0 z-10 -mx-8 border-b border-border bg-background/85 px-8 py-3 backdrop-blur">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <FilterField label={t("season", "Saison")}>
          <SelectControl
            value={props.season}
            onChange={props.onSeasonChange}
            disabled={props.seasonsLoading}
            ariaLabel={t("season", "Saison")}
          >
            <option value="latest">{t("season_latest", "Aktuelle Saison")}</option>
            {props.seasons.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </SelectControl>
        </FilterField>

        <FilterField label={t("league", "Liga")}>
          <SelectControl
            value={props.league}
            onChange={props.onLeagueChange}
            disabled={props.leaguesLoading}
            ariaLabel={t("league", "Liga")}
          >
            <option value="">{t("league_all", "Alle Ligen")}</option>
            {props.leagues.map((l) => (
              <option key={l.value} value={l.value}>
                {l.long_name || l.short_name}
              </option>
            ))}
          </SelectControl>
        </FilterField>

        {showWeek && (
          <FilterField label={t("week", "Spieltag")}>
            <SelectControl
              value={props.week}
              onChange={props.onWeekChange}
              disabled={props.weeksLoading}
              ariaLabel={t("week", "Spieltag")}
            >
              <option value="">{t("week_all", "Alle Spieltage")}</option>
              {props.weeks.map((w) => (
                <option key={w} value={String(w)}>
                  {w}
                </option>
              ))}
            </SelectControl>
          </FilterField>
        )}

        {showTeam && (
          <FilterField label={t("team", "Mannschaft")}>
            <SelectControl
              value={props.team}
              onChange={props.onTeamChange}
              disabled={props.teamsLoading}
              ariaLabel={t("team", "Mannschaft")}
            >
              <option value="">{t("team_all", "Alle Mannschaften")}</option>
              {props.teams.map((tm) => (
                <option key={tm} value={tm}>
                  {tm}
                </option>
              ))}
            </SelectControl>
          </FilterField>
        )}

        {showRound && (
          <FilterField label={t("game", "Spiel")}>
            <SelectControl
              value={props.round}
              onChange={props.onRoundChange}
              disabled={props.roundsLoading}
              ariaLabel={t("game", "Spiel")}
            >
              <option value="">{t("game_all", "Alle Spiele")}</option>
              {props.rounds.map((r) => (
                <option key={r} value={String(r)}>
                  {r}
                </option>
              ))}
            </SelectControl>
          </FilterField>
        )}
      </div>
    </div>
  );
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-label uppercase text-muted">{label}</span>
      {children}
    </label>
  );
}

function SelectControl({
  value,
  onChange,
  disabled,
  ariaLabel,
  children,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  ariaLabel: string;
  children: React.ReactNode;
}) {
  return (
    <select
      aria-label={ariaLabel}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 min-w-[160px] rounded-sm border border-border bg-surface px-2.5 text-small text-foreground hover:border-border-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60"
    >
      {children}
    </select>
  );
}

function seasonDisplay(season: string): string {
  return season === "latest" ? "—" : season;
}
