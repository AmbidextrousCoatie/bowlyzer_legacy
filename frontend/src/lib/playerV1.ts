import type {
  IndividualGameRecord,
  PlayerPeriodRow,
  PlayerSearchEntry,
  PlayerSeasonRow,
  PlayerStatsResponse,
} from "../hooks/usePlayer";
import { PLAYER_HIGHLIGHTS_TOP_N_ALL } from "./playerHighlights";
import { fetchV1 } from "./v1";

function optStr(value: unknown): string | null {
  if (value == null || value === "") return null;
  return String(value);
}

function optNum(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function optBool(value: unknown): boolean | null {
  if (value == null || value === "") return null;
  return Boolean(value);
}

function teamNumber(raw: Record<string, unknown>, teamName: string | null): number | null {
  const explicit = optNum(raw.team_number);
  if (explicit != null) return explicit;
  const match = String(teamName ?? "").match(/ (\d+)$/);
  return match ? Number(match[1]) : null;
}

function scoreBag(value: unknown): { score?: number | null } | null {
  if (value == null) return null;
  if (typeof value === "number") return { score: value };
  if (typeof value === "object") {
    const rec = value as Record<string, unknown>;
    return { score: optNum(rec.score) };
  }
  return null;
}

function aliasList(value: unknown, canonical: string): string[] {
  const names = Array.isArray(value) ? value : [];
  const seen = new Set<string>([canonical]);
  const aliases: string[] = [];
  for (const item of names) {
    const alias = optStr(item) ?? "";
    if (!alias || seen.has(alias)) continue;
    seen.add(alias);
    aliases.push(alias);
  }
  return aliases;
}

export function playerSearchFromV1(raw: Record<string, unknown> | unknown[]): PlayerSearchEntry[] {
  const rows = Array.isArray(raw) ? raw : raw.players;
  if (!Array.isArray(rows)) return [];
  const byId = new Map<string, PlayerSearchEntry>();
  const unnamed: PlayerSearchEntry[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const rec = row as Record<string, unknown>;
    const name = optStr(rec.name ?? rec.player_name) ?? "";
    const id = optStr(rec.id ?? rec.player_id) ?? "";
    if (!name) continue;
    const aliases = aliasList(rec.aliases, name);
    if (!id) {
      unnamed.push({ id: "", name, aliases });
      continue;
    }
    const existing = byId.get(id);
    if (!existing) {
      byId.set(id, { id, name, aliases });
      continue;
    }
    const extra = new Set(existing.aliases ?? []);
    if (name !== existing.name) extra.add(name);
    for (const alias of aliases) extra.add(alias);
    extra.delete(existing.name);
    existing.aliases = [...extra];
  }
  return [...byId.values(), ...unnamed];
}

export function playerSeasonsFromV1(raw: Record<string, unknown> | unknown[]): string[] {
  const rows = Array.isArray(raw) ? raw : raw.seasons;
  if (!Array.isArray(rows)) return [];
  return rows.map((value) => String(value ?? "").trim()).filter(Boolean);
}

function seasonRowFromV1(raw: Record<string, unknown>): PlayerSeasonRow {
  const teamName = optStr(raw.team_name ?? raw.team);
  return {
    season: optStr(raw.season),
    competition: optStr(raw.competition ?? raw.event),
    is_tournament: optBool(raw.is_tournament),
    row_type: optStr(raw.row_type),
    club: optStr(raw.club),
    history_club: optStr(raw.history_club ?? raw.club),
    team_name: teamName,
    team_number: teamNumber(raw, teamName),
    player_name: optStr(raw.player_name),
    player_id: optStr(raw.player_id),
    games: optNum(raw.games),
    total_pins: optNum(raw.total_pins ?? raw.pins),
    average: optNum(raw.average),
    vs_last_season: optNum(raw.vs_last_season),
    rank: optNum(raw.rank),
    competitors: optNum(raw.competitors),
    best_game: scoreBag(raw.best_game),
    worst_game: scoreBag(raw.worst_game),
  };
}

function periodRowFromV1(raw: Record<string, unknown>): PlayerPeriodRow {
  const teamName = optStr(raw.team_name ?? raw.team);
  return {
    season: optStr(raw.season),
    competition: optStr(raw.competition ?? raw.event),
    is_tournament: optBool(raw.is_tournament),
    period_kind: optStr(raw.period_kind),
    period_value: optStr(raw.period_value),
    period_number: optNum(raw.period_number),
    player_name: optStr(raw.player_name),
    player_id: optStr(raw.player_id),
    games: optNum(raw.games),
    average: optNum(raw.average),
    club: optStr(raw.club),
    team_name: teamName,
    team_number: teamNumber(raw, teamName),
    row_type: optStr(raw.row_type),
  };
}

function objectRows(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (row): row is Record<string, unknown> => Boolean(row) && typeof row === "object",
  );
}

export function playerStatsFromV1(
  raw: Record<string, unknown> | null | undefined,
): PlayerStatsResponse {
  if (!raw || typeof raw !== "object") return null;
  const lifetimeRaw = raw.lifetime;
  const lifetime =
    lifetimeRaw && typeof lifetimeRaw === "object"
      ? (() => {
          const rec = lifetimeRaw as Record<string, unknown>;
          const bestGame =
            rec.best_game && typeof rec.best_game === "object"
              ? (rec.best_game as Record<string, unknown>)
              : {};
          const bestSeason =
            rec.best_season && typeof rec.best_season === "object"
              ? (rec.best_season as Record<string, unknown>)
              : {};
          const most =
            rec.most_improved && typeof rec.most_improved === "object"
              ? (rec.most_improved as Record<string, unknown>)
              : {};
          return {
            total_games: optNum(rec.total_games),
            total_pins: optNum(rec.total_pins),
            average_score: optNum(rec.average_score ?? rec.average),
            best_game: {
              score: optNum(bestGame.score ?? rec.best_game),
              event: optStr(bestGame.event),
              date: optStr(bestGame.date),
            },
            best_season: {
              season: optStr(bestSeason.season ?? rec.best_season),
              average: optNum(bestSeason.average),
              player_name: optStr(bestSeason.player_name),
            },
            most_improved: {
              season: optStr(most.season),
              improvement: optNum(most.improvement ?? most.vs_last_season),
              player_name: optStr(most.player_name),
            },
          };
        })()
      : null;
  if (!lifetime && objectRows(raw.seasons).length === 0) return null;
  return {
    scope: raw.scope === "all" ? "all" : "player",
    lifetime,
    seasons: objectRows(raw.seasons).map(seasonRowFromV1),
    periods: objectRows(raw.periods).map(periodRowFromV1),
    player_competitions: objectRows(raw.player_competitions).map(seasonRowFromV1),
    player_season_totals: objectRows(raw.player_season_totals).map(seasonRowFromV1),
  };
}

export function highestGamesFromV1(
  raw: Record<string, unknown> | unknown[],
): IndividualGameRecord[] {
  const rows = Array.isArray(raw) ? raw : (raw.games ?? raw.highlights);
  if (!Array.isArray(rows)) return [];
  return rows
    .filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object")
    .map((row) => {
      const teamName = optStr(row.team_name ?? row.team);
      const round =
        row.round_number != null && row.round_number !== "" ? row.round_number : row.round;
      return {
        player_name: optStr(row.player_name ?? row.player),
        player_id: optStr(row.player_id),
        score: optNum(row.score),
        date: optStr(row.date ?? row.game_date),
        season: optStr(row.season),
        competition: optStr(row.competition ?? row.event),
        is_tournament: Boolean(row.is_tournament),
        club: optStr(row.club),
        team_name: teamName,
        team_number: teamNumber(row, teamName),
        week: optNum(row.week),
        round_number: optNum(round),
      };
    })
    .filter((row) => row.player_name);
}

export async function loadPlayerSearch(club?: string | null): Promise<PlayerSearchEntry[]> {
  const raw = await fetchV1<Record<string, unknown>>("/api/v1/players", {
    club: club || undefined,
    limit: 20_000,
  });
  return playerSearchFromV1(raw);
}

export async function loadPlayerSeasons(
  playerName: string,
  playerId: string,
  club?: string | null,
): Promise<string[]> {
  const raw = await fetchV1<Record<string, unknown>>("/api/v1/players/seasons", {
    player_id: playerId || undefined,
    player: playerName || undefined,
    club: club || undefined,
  });
  return playerSeasonsFromV1(raw);
}

export async function loadPlayerLifetimeStats(
  playerName: string,
  playerId: string,
  season: string,
  club?: string | null,
  topN?: number,
): Promise<PlayerStatsResponse> {
  const raw = await fetchV1<Record<string, unknown>>("/api/v1/players/stats", {
    player_id: playerId || undefined,
    player: playerName || undefined,
    club: club || undefined,
    season: season || "all",
    top_n: playerName || playerId ? undefined : (topN ?? PLAYER_HIGHLIGHTS_TOP_N_ALL),
  });
  return playerStatsFromV1(raw);
}

export async function loadHighestIndividualGames(options: {
  limit?: number;
  playerName?: string;
  playerId?: string;
  season?: string;
  club?: string | null;
}): Promise<IndividualGameRecord[]> {
  const raw = await fetchV1<Record<string, unknown>>("/api/v1/players/highlights", {
    limit: options.limit ?? 10,
    player_id: options.playerId || undefined,
    player: options.playerName || undefined,
    club: options.club || undefined,
    season: options.season || "all",
  });
  return highestGamesFromV1(raw);
}
