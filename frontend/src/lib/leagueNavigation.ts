import type { ColumnGroup } from "./datatable/types";
import { seasonForUrlQuery } from "./api";
import { searchParamsForPath } from "./navigationQuery";

export type LeagueNavTarget =
  | { view: "league-season" }
  | { view: "league-team"; team: string }
  | { view: "league-week"; week?: number | string }
  | { view: "league-week-team"; week?: number | string; team: string }
  | { view: "league-game"; week?: number | string; team: string; round: number | string };

export type LeagueNavContext = {
  season: string;
  league: string;
  /** Latest week on season standings (group 0 / header). */
  defaultWeek: number | string;
  /** Currently selected Spieltag; ranking / averages keep it when set. */
  week?: number | string | null;
  /** Current `/liga` query so drill-down links keep `database`, `myClub`, etc. */
  sourceQuery?: string;
};

export type LigaTableNavKind = "standings" | "teamVsTeam" | "averages";

export type TeamVsTeamMatchupNav = {
  week: number | string;
  round?: number | string;
};

function sourceParams(ctx: LeagueNavContext): URLSearchParams {
  return searchParamsForPath("/liga", new URLSearchParams(ctx.sourceQuery ?? ""));
}

export function buildLeagueNavPath(target: LeagueNavTarget, ctx: LeagueNavContext): string {
  const qs = sourceParams(ctx);
  qs.set("season", seasonForUrlQuery(ctx.season));
  qs.set("league", ctx.league);
  qs.delete("week");
  qs.delete("team");
  qs.delete("round");
  qs.delete("level");
  qs.delete("division");
  if (target.view === "league-season") {
    return `/liga?${qs.toString()}`;
  }
  if (target.view === "league-team") {
    qs.set("team", target.team);
    return `/liga?${qs.toString()}`;
  }
  qs.set("week", String(target.week ?? ctx.week ?? ctx.defaultWeek));
  if (target.view === "league-week-team" || target.view === "league-game") {
    qs.set("team", target.team);
  }
  if (target.view === "league-game") {
    qs.set("round", String(target.round));
  }
  return `/liga?${qs.toString()}`;
}

function hasWeek(ctx: LeagueNavContext, week?: number | string | null): boolean {
  const value = week ?? ctx.week;
  return value != null && String(value) !== "";
}

function teamDrillTarget(
  team: string,
  ctx: LeagueNavContext,
  week?: number | string | null,
): LeagueNavTarget {
  if (hasWeek(ctx, week)) {
    return { view: "league-week-team", team, week: week ?? ctx.week ?? undefined };
  }
  return { view: "league-team", team };
}

/** Honor payloads: team on entry, or `Player (Team)` in player string. */
export function teamFromHonorEntry(entry: {
  player?: string;
  player_name?: string;
  team?: string;
  team_name?: string;
  name?: string;
}): string | null {
  if (entry.team?.trim()) return entry.team.trim();
  if (entry.team_name?.trim()) return entry.team_name.trim();
  const label = entry.player ?? entry.player_name ?? entry.name;
  if (!label) return null;
  const m = label.match(/\(([^)]+)\)\s*$/);
  return m ? m[1].trim() : null;
}

/** Bestleistungen → team week view (no player page yet); game when round is known. */
/** Team stats “Besondere Momente” → game sheet when round is known, else week sheet. */
export function resolveSpecialMatchNavPath(
  match: {
    Season?: string;
    League?: string;
    Week?: number | string | null;
    Round?: number | string | null;
  },
  teamName: string,
  sourceQuery?: string,
): string | null {
  const season = match.Season != null ? String(match.Season).trim() : "";
  const league = match.League != null ? String(match.League).trim() : "";
  const week = match.Week;
  if (!season || !league || week === undefined || week === null || String(week) === "") {
    return null;
  }
  const round = match.Round;
  const hasRound =
    round !== undefined && round !== null && String(round) !== "" && String(round) !== "0";
  const ctx: LeagueNavContext = { season, league, defaultWeek: week, sourceQuery };
  if (hasRound) {
    return buildLeagueNavPath({ view: "league-game", team: teamName, week, round }, ctx);
  }
  return buildLeagueNavPath({ view: "league-week-team", team: teamName, week }, ctx);
}

export function resolveHonorScoreNavPath(
  entry: {
    player?: string;
    player_name?: string;
    team?: string;
    team_name?: string;
    name?: string;
    round?: number | string;
    game?: number | string;
  },
  ctx: LeagueNavContext,
): string | null {
  const team = teamFromHonorEntry(entry);
  if (!team) return null;
  const round = entry.round ?? entry.game;
  if (round !== undefined && round !== null && String(round) !== "") {
    return buildLeagueNavPath({ view: "league-game", team, round }, ctx);
  }
  return buildLeagueNavPath({ view: "league-week-team", team }, ctx);
}

/** Read week number from a weekly column group (title or `weekN_*` field). */
export function weekFromColumnGroup(columns: ColumnGroup[], groupIndex: number): string | null {
  const group = columns[groupIndex];
  if (!group) return null;
  for (const col of group.columns ?? []) {
    if (col.field) {
      const m = col.field.match(/^week(\d+)_/);
      if (m) return m[1];
    }
  }
  const title = group.title?.trim() ?? "";
  const m = title.match(/(\d+)/);
  return m ? m[1] : null;
}

export function groupIndexFromCellElement(cellEl: HTMLElement): number | null {
  const groupClass = [...cellEl.classList].find((c) => c.startsWith("col-group-"));
  if (!groupClass) return null;
  const idx = parseInt(groupClass.replace("col-group-", ""), 10);
  return Number.isNaN(idx) ? null : idx;
}

export function isRankingNavField(field: string): boolean {
  return field === "pos" || field === "team";
}

export function resolveLeagueCellNavPath(
  field: string,
  groupIndex: number | null,
  team: string | null,
  columns: ColumnGroup[],
  ctx: LeagueNavContext,
): string | null {
  if (groupIndex === null) return null;
  if (groupIndex === 0) {
    if (!isRankingNavField(field) || !team) return null;
    return buildLeagueNavPath(teamDrillTarget(team, ctx), ctx);
  }
  if (groupIndex === 1) {
    return buildLeagueNavPath({ view: "league-season" }, ctx);
  }
  if (groupIndex >= 2) {
    const week = weekFromColumnGroup(columns, groupIndex);
    if (!week) return null;
    return buildLeagueNavPath({ view: "league-week", week }, ctx);
  }
  return null;
}

export function opponentFromTeamVsTeamField(field: string): string | null {
  if (
    !field ||
    field === "pos" ||
    field === "team" ||
    field === "avg_score" ||
    field === "avg_points"
  ) {
    return null;
  }
  if (field.endsWith("_score")) return field.slice(0, -"_score".length);
  if (field.endsWith("_points")) return field.slice(0, -"_points".length);
  return null;
}

export function matchupNavFromMetadata(
  metadata: Record<string, unknown> | undefined,
  team: string,
  opponent: string,
): TeamVsTeamMatchupNav | null {
  const matchups = metadata?.matchups;
  if (!matchups || typeof matchups !== "object") return null;
  const byTeam = (matchups as Record<string, unknown>)[team];
  if (!byTeam || typeof byTeam !== "object") return null;
  const nav = (byTeam as Record<string, unknown>)[opponent];
  if (!nav || typeof nav !== "object") return null;
  const week = (nav as { week?: unknown }).week;
  if (week == null || week === "") return null;
  const round = (nav as { round?: unknown }).round;
  const result: TeamVsTeamMatchupNav = { week: week as number | string };
  if (round != null && String(round) !== "") result.round = round as number | string;
  return result;
}

function cellHasMatchupValue(value: unknown): boolean {
  return value != null && value !== "";
}

export function resolveTeamVsTeamCellNavPath(
  field: string,
  team: string | null,
  value: unknown,
  metadata: Record<string, unknown> | undefined,
  ctx: LeagueNavContext,
): string | null {
  if (!team) return null;
  if (field === "pos" || field === "team" || field === "avg_score" || field === "avg_points") {
    return buildLeagueNavPath(teamDrillTarget(team, ctx), ctx);
  }
  const opponent = opponentFromTeamVsTeamField(field);
  if (!opponent || opponent === team) return null;
  if (!cellHasMatchupValue(value)) return null;
  const matchup = matchupNavFromMetadata(metadata, team, opponent);
  if (!matchup) {
    return buildLeagueNavPath(teamDrillTarget(team, ctx), ctx);
  }
  if (matchup.round != null && String(matchup.round) !== "") {
    return buildLeagueNavPath(
      { view: "league-game", team, week: matchup.week, round: matchup.round },
      ctx,
    );
  }
  return buildLeagueNavPath({ view: "league-week-team", team, week: matchup.week }, ctx);
}

export function resolveAveragesCellNavPath(
  team: string | null,
  ctx: LeagueNavContext,
): string | null {
  if (!team) return null;
  return buildLeagueNavPath(teamDrillTarget(team, ctx), ctx);
}
