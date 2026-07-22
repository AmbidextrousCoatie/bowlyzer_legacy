import type { ColumnGroup } from "./datatable/types";
import { seasonForUrlQuery } from "./api";

export type LeagueNavTarget =
  | { view: "league-season" }
  | { view: "league-week"; week?: number | string }
  | { view: "league-week-team"; week?: number | string; team: string }
  | { view: "league-game"; week?: number | string; team: string; round: number | string };

export type LeagueNavContext = {
  season: string;
  league: string;
  /** Latest week on season standings (group 0 / header). */
  defaultWeek: number | string;
};

export function buildLeagueNavPath(target: LeagueNavTarget, ctx: LeagueNavContext): string {
  const qs = new URLSearchParams();
  qs.set("season", seasonForUrlQuery(ctx.season));
  qs.set("league", ctx.league);
  if (target.view === "league-season") {
    return `/liga?${qs.toString()}`;
  }
  qs.set("week", String(target.week ?? ctx.defaultWeek));
  if (target.view === "league-week-team" || target.view === "league-game") {
    qs.set("team", target.team);
  }
  if (target.view === "league-game") {
    qs.set("round", String(target.round));
  }
  return `/liga?${qs.toString()}`;
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
  if (hasRound) {
    return buildLeagueNavPath(
      { view: "league-game", team: teamName, week, round },
      { season, league, defaultWeek: week },
    );
  }
  return buildLeagueNavPath(
    { view: "league-week-team", team: teamName, week },
    { season, league, defaultWeek: week },
  );
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
    return buildLeagueNavPath({ view: "league-week-team", team }, ctx);
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
