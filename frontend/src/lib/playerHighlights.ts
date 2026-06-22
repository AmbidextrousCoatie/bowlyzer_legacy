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
};

export const PLAYER_HIGHLIGHTS_TOP_N = 5;

export type PlayerHighlightEntry = {
  id: string;
  label: string;
  value: string;
  detail?: string;
  href?: string;
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

function formatRank(rank: number | null | undefined, competitors: number | null | undefined): string {
  if (rank == null || !Number.isFinite(rank)) return "—";
  return competitors ? `${rank} / ${competitors}` : String(rank);
}

export function buildPlayerHighlights(
  rows: PlayerSeasonRow[] | null | undefined,
  options?: PlayerHighlightsOptions,
  periods?: PlayerPeriodRow[] | null,
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
  if (!rows?.length) return empty;

  const { historyRows } = buildPlayerClubHistory(rows);
  const clubAffiliation: PlayerHighlightEntry[] = historyRows
    .slice(0, PLAYER_HIGHLIGHTS_TOP_N)
    .map((row, idx) => ({
      id: `club-${row.club}-${idx}`,
      label: row.club,
      value: row.period,
      href: buildUrl("/club", { club: row.club }),
    }));

  const byClub = new Map<string, { games: number; pins: number }>();
  for (const row of competitionRows(rows)) {
    const club = normalizeClub(row.club);
    if (!club) continue;
    const games = row.games ?? 0;
    const pins = row.total_pins ?? 0;
    const prev = byClub.get(club) ?? { games: 0, pins: 0 };
    byClub.set(club, { games: prev.games + games, pins: prev.pins + pins });
  }

  const gamesByClub: PlayerHighlightEntry[] = [...byClub.entries()]
    .sort((a, b) => b[1].games - a[1].games || a[0].localeCompare(b[0], "de"))
    .slice(0, PLAYER_HIGHLIGHTS_TOP_N)
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
    .slice(0, PLAYER_HIGHLIGHTS_TOP_N)
    .map((entry, idx) => ({
      id: `avg-club-${entry.club}-${idx}`,
      label: entry.club,
      value: formatAvg(entry.average),
      detail: `${entry.games} Spiele`,
      href: buildUrl("/club", { club: entry.club }),
    }));

  const avgBySeason: PlayerHighlightEntry[] = seasonTotalRows(rows)
    .filter((r) => r.average != null && Number.isFinite(r.average))
    .sort(
      (a, b) =>
        (b.average ?? 0) - (a.average ?? 0) ||
        compareSeasonString(String(a.season ?? ""), String(b.season ?? "")),
    )
    .slice(0, PLAYER_HIGHLIGHTS_TOP_N)
    .map((row, idx) => ({
      id: `avg-season-${row.season}-${idx}`,
      label: String(row.season ?? "—"),
      value: formatAvg(row.average),
      detail: row.games != null ? `${row.games} Spiele` : undefined,
    }));

  const bestTournaments: PlayerHighlightEntry[] = competitionRows(rows)
    .filter((r) => r.is_tournament && r.rank != null && Number.isFinite(r.rank))
    .sort(
      (a, b) =>
        (a.rank ?? 999) - (b.rank ?? 999) ||
        compareSeasonString(String(b.season ?? ""), String(a.season ?? "")),
    )
    .slice(0, PLAYER_HIGHLIGHTS_TOP_N)
    .map((row, idx) => {
      const fullName = String(row.competition ?? "—");
      return {
        id: `tournament-${row.competition}-${row.season}-${idx}`,
        label: formatCompetitionLabel(fullName, {
          isTournament: true,
          tournamentAbbreviations: options?.tournamentAbbreviations,
        }),
        title: fullName,
        value: formatRank(row.rank, row.competitors),
        detail: String(row.season ?? ""),
        href: options ? buildCompetitionEventPath(row, options) ?? undefined : undefined,
      };
    });

  const bestCompetitions: PlayerHighlightEntry[] = competitionRows(rows)
    .filter((r) => r.average != null && Number.isFinite(r.average))
    .sort(
      (a, b) =>
        (b.average ?? 0) - (a.average ?? 0) ||
        (b.games ?? 0) - (a.games ?? 0) ||
        String(a.competition ?? "").localeCompare(String(b.competition ?? ""), "de"),
    )
    .slice(0, PLAYER_HIGHLIGHTS_TOP_N)
    .map((row, idx) => {
      const fullName = String(row.competition ?? "—");
      const isTournament = !!row.is_tournament;
      const label = isTournament
        ? formatCompetitionLabel(fullName, {
            isTournament: true,
            tournamentAbbreviations: options?.tournamentAbbreviations,
          })
        : fullName;
      return {
        id: `comp-${row.competition}-${row.season}-${idx}`,
        label,
        title: isTournament ? fullName : undefined,
        value: formatAvg(row.average),
        detail: [row.season, row.games != null ? `${row.games} Spiele` : null]
          .filter(Boolean)
          .join(" · "),
        href: options ? buildCompetitionEventPath(row, options) ?? undefined : undefined,
      };
    });

  const formatPeriod = options?.formatPeriod;
  const bestDays: PlayerHighlightEntry[] = (periods ?? [])
    .filter((r) => r.average != null && Number.isFinite(r.average))
    .sort(
      (a, b) =>
        (b.average ?? 0) - (a.average ?? 0) ||
        (b.games ?? 0) - (a.games ?? 0) ||
        compareSeasonString(String(b.season ?? ""), String(a.season ?? "")),
    )
    .slice(0, PLAYER_HIGHLIGHTS_TOP_N)
    .map((row, idx) => {
      const fullName = String(row.competition ?? "—");
      const isTournament = !!row.is_tournament;
      const compLabel = isTournament
        ? formatCompetitionLabel(fullName, {
            isTournament: true,
            tournamentAbbreviations: options?.tournamentAbbreviations,
          })
        : fullName;
      const headline = formatCompetitionWithSeason(compLabel, row.season);
      const periodDetail = formatPeriod ? formatPeriod(row) : String(row.period_value ?? "");
      return {
        id: `day-${row.competition}-${row.season}-${row.period_kind}-${row.period_number}-${idx}`,
        label: headline,
        title: [fullName, periodDetail].filter(Boolean).join(" · "),
        value: formatAvg(row.average),
        detail: periodDetail,
        href: options ? buildPeriodEventPath(row, options) ?? undefined : undefined,
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
