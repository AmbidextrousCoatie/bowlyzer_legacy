import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../lib/api";
import { normalizeHonorCards } from "../lib/honorCards";
import type { ChartData, HonorCardView, ListData, OptionItem, TableData, TeamWeekView } from "../types";

type BaseFilters = {
  database: string;
  league: string;
  season: string;
  week: string;
  team: string;
};

export function useLeagueOptions({ database, league, season }: Pick<BaseFilters, "database" | "league" | "season">) {
  const [leagues, setLeagues] = useState<OptionItem[]>([]);
  const [seasons, setSeasons] = useState<OptionItem[]>([]);
  const [weeks, setWeeks] = useState<OptionItem[]>([]);
  const [teams, setTeams] = useState<OptionItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<ListData>("/api/v1/league/options/leagues", { database })
      .then((d) => setLeagues(d.items))
      .catch((e: Error) => setError(e.message));
  }, [database]);

  useEffect(() => {
    if (!league) return;
    apiGet<ListData>("/api/v1/league/options/seasons", { league, database })
      .then((d) => setSeasons(d.items))
      .catch((e: Error) => setError(e.message));
  }, [league, database]);

  useEffect(() => {
    if (!league || !season) return;
    apiGet<ListData>("/api/v1/league/options/weeks", { league, season, database })
      .then((d) => setWeeks(d.items))
      .catch((e: Error) => setError(e.message));
    apiGet<ListData>("/api/v1/league/options/teams", { league, season, database })
      .then((d) => setTeams(d.items))
      .catch((e: Error) => setError(e.message));
  }, [league, season, database]);

  return { leagues, seasons, weeks, teams, error };
}

export function useCoreViews({ database, league, season, week }: Pick<BaseFilters, "database" | "league" | "season" | "week">) {
  const [standings, setStandings] = useState<TableData | null>(null);
  const [pointsChart, setPointsChart] = useState<ChartData | null>(null);
  const [teamVsTeam, setTeamVsTeam] = useState<TableData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!league || !season) return;
    setLoading(true);
    setError(null);
    try {
      const [standingsData, pointsData] = await Promise.all([
        apiGet<TableData>("/api/v1/league/season/standings", { league, season, database }),
        apiGet<ChartData>("/api/v1/league/season/team-points", { league, season, week, database }),
      ]);
      setStandings(standingsData);
      setPointsChart(pointsData);
      const t2tData = await apiGet<TableData>("/api/v1/league/season/team-vs-team", { league, season, week, database });
      setTeamVsTeam(t2tData);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [database, league, season, week]);

  useEffect(() => {
    if (league && season) void refresh();
  }, [league, season, database, refresh]);

  return { standings, pointsChart, teamVsTeam, loading, error, refresh };
}

export function useMatchdayViews({ database, league, season, week }: Pick<BaseFilters, "database" | "league" | "season" | "week">) {
  const [matchdayStandings, setMatchdayStandings] = useState<TableData | null>(null);
  const [honorCards, setHonorCards] = useState<HonorCardView[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!league || !season || !week) return;
    setLoading(true);
    setError(null);
    try {
      const [standingsData, honorData] = await Promise.all([
        apiGet<TableData>("/api/v1/league/matchday/standings", { league, season, week, database }),
        apiGet<{ cards: unknown }>("/api/v1/league/matchday/honor-scores", { league, season, week, database }),
      ]);
      setMatchdayStandings(standingsData);
      setHonorCards(normalizeHonorCards(honorData.cards));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [database, league, season, week]);

  useEffect(() => {
    if (league && season && week) void refresh();
  }, [league, season, week, database, refresh]);

  return { matchdayStandings, honorCards, loading, error, refresh };
}

export function useTeamWeekViews({ database, league, season, week, team }: BaseFilters) {
  const [teamWeekView, setTeamWeekView] = useState<TeamWeekView>("classic");
  const [teamWeekTable, setTeamWeekTable] = useState<TableData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(
    async (view: TeamWeekView = teamWeekView) => {
      if (!league || !season || !week || !team) return;
      setLoading(true);
      setError(null);
      setTeamWeekView(view);
      try {
        let path = "/api/v1/league/team-week/classic";
        const params: Record<string, string | undefined> = { league, season, week, team, database };
        if (view === "individual") path = "/api/v1/league/team-week/individual-scores";
        if (view === "head-to-head") {
          path = "/api/v1/league/team-week/head-to-head";
          params.viewMode = "own_team";
        }
        const tableData = await apiGet<TableData>(path, params);
        setTeamWeekTable(tableData);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    },
    [database, league, season, team, teamWeekView, week],
  );

  useEffect(() => {
    if (league && season && week && team) void refresh(teamWeekView);
  }, [league, season, week, team, teamWeekView, database, refresh]);

  return { teamWeekView, teamWeekTable, loading, error, refresh };
}
