import type { PlayerPeriodRow, PlayerSeasonRow } from "../hooks/usePlayer";
import { buildPlayerClubHistory, compareSeasonString } from "./playerClubHistory";
import { buildUrl } from "./api";
import {
  buildCompetitionEventPath,
  buildPeriodEventPath,
  type CompetitionLinkContext,
} from "./playerCompetitionLinks";
import { formatCompetitionLabel } from "./competitionDisplayName";
import {
  formatCompetitionWithSeason,
} from "./playerPeriodLabel";

export type { CompetitionLinkContext };

export type PlayerHighlightsOptions = CompetitionLinkContext & {
  tournamentAbbreviations?: Record<string, string>;
  formatPeriod?: (row: PlayerPeriodRow) => string;
  /** When set, season averages need at least this many games. */
  minGamesAvgBySeason?: number;
  /** When set, competition averages need at least this many games. */
  minGamesBestCompetitions?: number;
  /** When set, league week averages need at least this many games. */
  minGamesBestDays?: number;
  /** With minGamesBestDays: only non-tournament week/round rows. */
  leagueWeeksOnlyBestDays?: boolean;
};

export const PLAYER_HIGHLIGHTS_TOP_N_ALL = 10;
export const PLAYER_HIGHLIGHTS_TOP_N_PLAYER = 5;
export const PLAYER_HIGHLIGHTS_MIN_GAMES_SEASON = 10;
export const PLAYER_HIGHLIGHTS_MIN_GAMES_COMPETITION = 10;
export const PLAYER_HIGHLIGHTS_MIN_GAMES_LEAGUE_WEEK = 5;

/** @deprecated Use {@link playerHighlightsTopN} */
export const PLAYER_HIGHLIGHTS_TOP_N = PLAYER_HIGHLIGHTS_TOP_N_ALL;

export function playerHighlightsTopN(scope: "all" | "player"): number {
  return scope === "all" ? PLAYER_HIGHLIGHTS_TOP_N_ALL : PLAYER_HIGHLIGHTS_TOP_N_PLAYER;
}

export type BuildPlayerHighlightsArgs = {
  scope: "all" | "player";
  seasons: PlayerSeasonRow[];
  periods?: PlayerPeriodRow[];
  playerCompetitions?: PlayerSeasonRow[];
  playerSeasonTotals?: PlayerSeasonRow[];
};

export type PlayerHighlightEntry = {
  id: string;
  label: string;
  value: string;
  detail?: string;
  href?: string;
  /** Optional secondary link (e.g. competition) shown on the detail line. */
  detailHref?: string;
  /** Full competition name for tooltips when ``label`` is abbreviated. */
  title?: string;
};

export type PlayerHighlightsData = {
  clubAffiliation: PlayerHighlightEntry[];
  gamesByClub: PlayerHighlightEntry[];
  avgByClub: PlayerHighlightEntry[];
  avgBySeason: PlayerHighlightEntry[];
  bestTournaments: PlayerHighlightEntry[];
  bestCompetitions: PlayerHighlightEntry[];
  bestDays: PlayerHighlightEntry[];
};

function competitionRows(rows: PlayerSeasonRow[]): PlayerSeasonRow[] {
  return rows.filter((r) => String(r.row_type ?? "").trim() === "competition");
}

function seasonTotalRows(rows: PlayerSeasonRow[]): PlayerSeasonRow[] {
  return rows.filter((r) => String(r.row_type ?? "").trim() === "season_total");
}

function normalizeClub(raw: string | null | undefined): string | null {
  const s = String(raw ?? "").trim();
  if (!s || s === "-" || s === "—") return null;
  return s;
}

function formatAvg(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toFixed(2);
}

function meetsMinGames(games: number | null | undefined, minGames?: number): boolean {
  if (minGames == null || minGames <= 0) return true;
  return (games ?? 0) >= minGames;
}

function isLeagueWeekPeriod(row: PlayerPeriodRow): boolean {
  if (row.is_tournament) return false;
  const kind = String(row.period_kind ?? "").trim().toLowerCase();
  return kind === "week" || kind === "round" || kind === "";
}

function formatRank(rank: number | null | undefined, competitors: number | null | undefined): string {
  if (rank == null || !Number.isFinite(rank)) return "—";
  return competitors ? `${rank} / ${competitors}` : String(rank);
}

function playerPageHref(name: string, id?: string | null): string {
  const params: Record<string, string> = { player_name: name };
  if (id) params.player_id = id;
  return buildUrl("/spieler", params);
}

function joinDetail(...parts: Array<string | number | null | undefined>): string | undefined {
  const text = parts.map((p) => String(p ?? "").trim()).filter(Boolean).join(" · ");
  return text || undefined;
}

function buildAllPlayersClubAffiliation(
  rows: PlayerSeasonRow[],
  topN: number,
): PlayerHighlightEntry[] {
  const byPlayer = new Map<string, PlayerSeasonRow[]>();
  for (const row of competitionRows(rows)) {
    const player = String(row.player_name ?? "").trim();
    if (!player) continue;
    const list = byPlayer.get(player) ?? [];
    list.push(row);
    byPlayer.set(player, list);
  }

  return [...byPlayer.entries()]
    .map(([player, playerRows]) => {
      const { historyRows } = buildPlayerClubHistory(playerRows);
      const latest = historyRows[0];
      if (!latest) return null;
      const games = playerRows.reduce((sum, row) => sum + (row.games ?? 0), 0);
      const playerId = String(playerRows.find((r) => r.player_id)?.player_id ?? "").trim();
      return {
        player,
        playerId,
        club: latest.club,
        period: latest.period,
        games,
      };
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry != null)
    .sort((a, b) => b.games - a.games || a.player.localeCompare(b.player, "de"))
    .slice(0, topN)
    .map((entry, idx) => ({
      id: `club-aff-${entry.player}-${idx}`,
      label: entry.player,
      value: entry.club,
      detail: joinDetail(entry.period, `${entry.games} Spiele`),
      href: playerPageHref(entry.player, entry.playerId),
      title: `${entry.player} · ${entry.club}`,
    }));
}

export function buildPlayerHighlights(
  input: BuildPlayerHighlightsArgs,
  options?: PlayerHighlightsOptions,
): PlayerHighlightsData {
  const empty: PlayerHighlightsData = {
    clubAffiliation: [],
    gamesByClub: [],
    avgByClub: [],
    avgBySeason: [],
    bestTournaments: [],
    bestCompetitions: [],
    bestDays: [],
  };

  const scope = input.scope;
  const topN = playerHighlightsTopN(scope);
  const chartRows = input.seasons ?? [];
  const highlightCompetitions =
    scope === "all" ? (input.playerCompetitions ?? []) : competitionRows(chartRows);
  const highlightSeasonTotals =
    scope === "all" ? (input.playerSeasonTotals ?? []) : seasonTotalRows(chartRows);
  const periods = input.periods ?? [];

  if (!chartRows.length && !highlightCompetitions.length && !periods.length) return empty;

  const clubAffiliation: PlayerHighlightEntry[] =
    scope === "all"
      ? buildAllPlayersClubAffiliation(highlightCompetitions, topN)
      : (() => {
          const { historyRows } = buildPlayerClubHistory(chartRows);
          return historyRows.slice(0, topN).map((row, idx) => ({
            id: `club-${row.club}-${idx}`,
            label: row.club,
            value: row.period,
            detail: options?.selectedPlayerName || undefined,
            href: buildUrl("/club", { club: row.club }),
          }));
        })();

  const byClub = new Map<string, { games: number; pins: number }>();
  const clubSourceRows = scope === "all" ? highlightCompetitions : competitionRows(chartRows);
  for (const row of clubSourceRows) {
    const club = normalizeClub(row.club);
    if (!club) continue;
    const games = row.games ?? 0;
    const pins = row.total_pins ?? 0;
    const prev = byClub.get(club) ?? { games: 0, pins: 0 };
    byClub.set(club, { games: prev.games + games, pins: prev.pins + pins });
  }

  const gamesByClub: PlayerHighlightEntry[] = [...byClub.entries()]
    .sort((a, b) => b[1].games - a[1].games || a[0].localeCompare(b[0], "de"))
    .slice(0, topN)
    .map(([club, stats], idx) => ({
      id: `games-${club}-${idx}`,
      label: club,
      value: String(stats.games),
      detail: `Ø ${formatAvg(stats.games > 0 ? stats.pins / stats.games : null)}`,
      href: buildUrl("/club", { club }),
    }));

  const avgByClub: PlayerHighlightEntry[] = [...byClub.entries()]
    .map(([club, stats]) => ({
      club,
      games: stats.games,
      average: stats.games > 0 ? stats.pins / stats.games : null,
    }))
    .filter((e) => e.games > 0 && e.average != null)
    .sort(
      (a, b) =>
        (b.average ?? 0) - (a.average ?? 0) ||
        (b.games ?? 0) - (a.games ?? 0) ||
        a.club.localeCompare(b.club, "de"),
    )
    .slice(0, topN)
    .map((entry, idx) => ({
      id: `avg-club-${entry.club}-${idx}`,
      label: entry.club,
      value: formatAvg(entry.average),
      detail: `${entry.games} Spiele`,
      href: buildUrl("/club", { club: entry.club }),
    }));

  const avgBySeason: PlayerHighlightEntry[] = highlightSeasonTotals
    .filter(
      (r) =>
        r.average != null &&
        Number.isFinite(r.average) &&
        meetsMinGames(r.games, options?.minGamesAvgBySeason),
    )
    .sort(
      (a, b) =>
        (b.average ?? 0) - (a.average ?? 0) ||
        compareSeasonString(String(a.season ?? ""), String(b.season ?? "")),
    )
    .slice(0, topN)
    .map((row, idx) => {
      const player = String(row.player_name ?? "").trim();
      const club = normalizeClub(row.club);
      return {
        id: `avg-season-${row.season}-${player || idx}`,
        label: scope === "all" && player ? player : String(row.season ?? "—"),
        value: formatAvg(row.average),
        detail: joinDetail(
          scope === "all" ? String(row.season ?? "") : undefined,
          club,
          row.games != null ? `${row.games} Spiele` : undefined,
        ),
        href: scope === "all" && player ? playerPageHref(player, row.player_id) : undefined,
        title: scope === "all" && player ? `${player} · ${row.season}` : undefined,
      };
    });

  const bestTournaments: PlayerHighlightEntry[] = highlightCompetitions
    .filter((r) => r.is_tournament && r.rank != null && Number.isFinite(r.rank))
    .sort(
      (a, b) =>
        (a.rank ?? 999) - (b.rank ?? 999) ||
        compareSeasonString(String(b.season ?? ""), String(a.season ?? "")),
    )
    .slice(0, topN)
    .map((row, idx) => {
      const fullName = String(row.competition ?? "—");
      const player = String(row.player_name ?? "").trim();
      const club = normalizeClub(row.club);
      return {
        id: `tournament-${row.competition}-${row.season}-${player || idx}`,
        label:
          scope === "all" && player
            ? player
            : formatCompetitionLabel(fullName, {
                isTournament: true,
                tournamentAbbreviations: options?.tournamentAbbreviations,
              }),
        title: fullName,
        value: formatRank(row.rank, row.competitors),
        detail: joinDetail(
          formatCompetitionLabel(fullName, {
            isTournament: true,
            tournamentAbbreviations: options?.tournamentAbbreviations,
          }),
          row.season,
          club,
        ),
        href:
          scope === "all" && player
            ? playerPageHref(player, row.player_id)
            : options
              ? buildCompetitionEventPath(row, options) ?? undefined
              : undefined,
      };
    });

  const bestCompetitions: PlayerHighlightEntry[] = highlightCompetitions
    .filter(
      (r) =>
        r.average != null &&
        Number.isFinite(r.average) &&
        meetsMinGames(r.games, options?.minGamesBestCompetitions),
    )
    .sort(
      (a, b) =>
        (b.average ?? 0) - (a.average ?? 0) ||
        (b.games ?? 0) - (a.games ?? 0) ||
        String(a.competition ?? "").localeCompare(String(b.competition ?? ""), "de"),
    )
    .slice(0, topN)
    .map((row, idx) => {
      const fullName = String(row.competition ?? "—");
      const isTournament = !!row.is_tournament;
      const player = String(row.player_name ?? "").trim();
      const club = normalizeClub(row.club);
      const compLabel = isTournament
        ? formatCompetitionLabel(fullName, {
            isTournament: true,
            tournamentAbbreviations: options?.tournamentAbbreviations,
          })
        : fullName;
      return {
        id: `comp-${row.competition}-${row.season}-${player || idx}`,
        label: scope === "all" && player ? player : compLabel,
        title: isTournament ? fullName : undefined,
        value: formatAvg(row.average),
        detail: joinDetail(compLabel, row.season, club, row.games != null ? `${row.games} Spiele` : null),
        href:
          scope === "all" && player
            ? playerPageHref(player, row.player_id)
            : options
              ? buildCompetitionEventPath(row, options) ?? undefined
              : undefined,
      };
    });

  const formatPeriod = options?.formatPeriod;
  const bestDaysSource = options?.leagueWeeksOnlyBestDays
    ? periods.filter(isLeagueWeekPeriod)
    : periods;
  const bestDays: PlayerHighlightEntry[] = bestDaysSource
    .filter(
      (r) =>
        r.average != null &&
        Number.isFinite(r.average) &&
        meetsMinGames(r.games, options?.minGamesBestDays),
    )
    .sort(
      (a, b) =>
        (b.average ?? 0) - (a.average ?? 0) ||
        (b.games ?? 0) - (a.games ?? 0) ||
        compareSeasonString(String(b.season ?? ""), String(a.season ?? "")),
    )
    .slice(0, topN)
    .map((row, idx) => {
      const fullName = String(row.competition ?? "—");
      const isTournament = !!row.is_tournament;
      const player = String(row.player_name ?? "").trim();
      const club = normalizeClub(row.club);
      const compLabel = isTournament
        ? formatCompetitionLabel(fullName, {
            isTournament: true,
            tournamentAbbreviations: options?.tournamentAbbreviations,
          })
        : fullName;
      const headline =
        scope === "all" && player
          ? player
          : formatCompetitionWithSeason(compLabel, row.season);
      const periodDetail = formatPeriod ? formatPeriod(row) : String(row.period_value ?? "");
      return {
        id: `day-${row.competition}-${row.season}-${row.period_kind}-${row.period_number}-${player || idx}`,
        label: headline,
        title: joinDetail(fullName, periodDetail, player, club),
        value: formatAvg(row.average),
        detail: joinDetail(formatCompetitionWithSeason(compLabel, row.season), periodDetail, club),
        href:
          scope === "all" && player
            ? playerPageHref(player, row.player_id)
            : options
              ? buildPeriodEventPath(row, options) ?? undefined
              : undefined,
      };
    });

  return {
    clubAffiliation,
    gamesByClub,
    avgByClub,
    avgBySeason,
    bestTournaments,
    bestCompetitions,
    bestDays,
  };
}

/** Running career average after each season (chronological). */
export function buildCumulativeSeasonAverages(
  seasonTotals: PlayerSeasonRow[],
): { season: string; average: number }[] {
  const sorted = [...seasonTotals].sort((a, b) =>
    compareSeasonString(String(a.season ?? ""), String(b.season ?? "")),
  );
  let pins = 0;
  let games = 0;
  return sorted.map((row) => {
    pins += row.total_pins ?? 0;
    games += row.games ?? 0;
    return {
      season: String(row.season ?? ""),
      average: games > 0 ? pins / games : 0,
    };
  });
}

export type SeasonTableFilter = "all" | "league" | "tournaments";

export function filterSeasonRows(
  rows: PlayerSeasonRow[],
  filter: SeasonTableFilter,
): PlayerSeasonRow[] {
  if (filter === "all") return rows;
  if (filter === "league") {
    return rows.filter(
      (r) =>
        String(r.row_type ?? "").trim() === "season_total" ||
        (String(r.row_type ?? "").trim() === "competition" && !r.is_tournament),
    );
  }
  return rows.filter(
    (r) => String(r.row_type ?? "").trim() === "competition" && !!r.is_tournament,
  );
}

export function formatTeamLabel(row: PlayerSeasonRow): string {
  if (String(row.row_type ?? "").trim() === "season_total") return "";
  if (row.team_name) return String(row.team_name).trim();
  const club = normalizeClub(row.club);
  if (club && row.team_number != null && String(row.team_number).trim() !== "") {
    return `${club} ${row.team_number}`;
  }
  if (club) return club;
  return "—";
}

export function formatTrendDelta(delta: number | null | undefined): string {
  if (delta == null || !Number.isFinite(delta)) return "—";
  const sign = delta > 0 ? "+" : "";
  return `${sign}${delta.toFixed(2)}`;
}
