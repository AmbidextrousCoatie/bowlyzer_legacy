import type {
  ClutchAnalysis,
  ConsistencyMetrics,
  LeagueComparison,
  SpecialMatchRow,
  SpecialMatches,
  TeamHistory,
} from "../hooks/useTeam";
import { getLeagueLevel } from "./leagueLevel";
import { fetchV1 } from "./v1";

export const DEFAULT_CLUTCH_THRESHOLD = 10;

type Dict = Record<string, unknown>;

function asRecord(value: unknown): Dict {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Dict) : {};
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asStr(value: unknown): string {
  if (value == null) return "";
  return String(value).trim();
}

function asNum(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

function seasonParam(season: string | null | undefined): string | undefined {
  if (!season || season === "all") return undefined;
  return season;
}

export function teamsFromV1(raw: unknown): string[] {
  return asList(asRecord(raw).teams)
    .map(asStr)
    .filter(Boolean);
}

export function seasonsFromV1(raw: unknown): string[] {
  return asList(asRecord(raw).seasons)
    .map(asStr)
    .filter(Boolean);
}

export function historyFromV1(raw: unknown): TeamHistory {
  const history = asRecord(asRecord(raw).history);
  const out: TeamHistory = {};
  for (const [season, value] of Object.entries(history)) {
    const row = asRecord(value);
    const stats = asRecord(row.statistics);
    const leagueName = asStr(row.league_name);
    out[season] = {
      league_name: leagueName,
      final_position: asNum(row.final_position) ?? 0,
      league_level: asNum(row.league_level) ?? getLeagueLevel(leagueName),
      statistics: {
        total_score: asNum(stats.total_score) ?? undefined,
        total_points: asNum(stats.total_points) ?? undefined,
        average_score: asNum(stats.average_score) ?? undefined,
        games_played: asNum(stats.games_played) ?? undefined,
        best_score: asNum(stats.best_score) ?? undefined,
        worst_score: asNum(stats.worst_score) ?? undefined,
      },
    };
  }
  return out;
}

export function leagueComparisonFromV1(raw: unknown): LeagueComparison {
  const leagues = asRecord(asRecord(raw).leagues);
  const out: LeagueComparison = {};
  for (const [season, value] of Object.entries(leagues)) {
    const row = asRecord(value);
    const teamAvg = asNum(row.team_average);
    const leagueAvg = asNum(row.league_average);
    const diff = asNum(row.vs_league_average);
    const rank = asNum(row.final_position ?? row.performance_rank);
    out[season] = {
      league_name: asStr(row.league_name),
      league_averages: {
        average_score: leagueAvg ?? undefined,
        num_teams: asNum(row.num_teams) ?? undefined,
      },
      team_performance: {
        team_average_score: teamAvg ?? undefined,
        vs_league_average: diff ?? undefined,
        performance_rank: rank ?? undefined,
      },
      performance_rank: rank ?? undefined,
      vs_league_average: diff ?? undefined,
    };
  }
  return out;
}

export function clutchFromV1(raw: unknown): ClutchAnalysis {
  const clutch = asRecord(asRecord(raw).clutch);
  const opponentRaw = asRecord(clutch.opponent_clutch);
  const opponent_clutch: Record<string, { wins: number; losses: number }> = {};
  for (const [name, value] of Object.entries(opponentRaw)) {
    const row = asRecord(value);
    opponent_clutch[name] = {
      wins: asNum(row.wins) ?? 0,
      losses: asNum(row.losses) ?? 0,
    };
  }
  return {
    total_games: asNum(clutch.total_games) ?? undefined,
    total_clutch_games: asNum(clutch.total_clutch_games) ?? undefined,
    total_clutch_wins: asNum(clutch.total_clutch_wins) ?? undefined,
    total_clutch_losses: asNum(clutch.total_clutch_losses) ?? undefined,
    clutch_percentage: asNum(clutch.clutch_percentage) ?? undefined,
    opponent_clutch,
  };
}

export function consistencyFromV1(raw: unknown): ConsistencyMetrics {
  const row = asRecord(asRecord(raw).consistency);
  const sample = asNum(row.sample);
  if (sample === 0 || asStr(row.error)) {
    return { error: asStr(row.error) || "No team data found" };
  }
  if (sample != null && sample < 2) {
    return { error: "Insufficient data for consistency analysis" };
  }
  return {
    mean_score: asNum(row.mean ?? row.mean_score) ?? undefined,
    std_deviation: asNum(row.std ?? row.std_deviation) ?? undefined,
    coefficient_of_variation:
      asNum(row.cv_percent ?? row.coefficient_of_variation) ?? undefined,
    consistency_rating: asStr(row.consistency_rating) || undefined,
    min_score: asNum(row.min ?? row.min_score) ?? undefined,
    max_score: asNum(row.max ?? row.max_score) ?? undefined,
    score_range: asNum(row.range ?? row.score_range) ?? undefined,
    iqr: asNum(row.iqr) ?? undefined,
  };
}

function specialRowFromV1(value: unknown): SpecialMatchRow {
  const row = asRecord(value);
  return {
    Season: asStr(row.season || row.Season),
    League: asStr(row.league || row.League),
    Week: asNum(row.week ?? row.Week) ?? undefined,
    Round: asNum(row.round ?? row.Round) ?? undefined,
    Score: asNum(row.score ?? row.Score) ?? undefined,
    Opponent: asStr(row.opponent || row.Opponent),
    OpponentScore: asNum(row.opponent_score ?? row.OpponentScore) ?? undefined,
    WinMargin: asNum(row.win_margin ?? row.WinMargin) ?? undefined,
  };
}

export function specialMatchesFromV1(raw: unknown): SpecialMatches {
  const block = asRecord(asRecord(raw).special_matches);
  return {
    highest_scores: asList(block.highest_scores).map(specialRowFromV1),
    lowest_scores: asList(block.lowest_scores).map(specialRowFromV1),
    biggest_win_margin: asList(block.biggest_win_margin).map(specialRowFromV1),
    biggest_loss_margin: asList(block.biggest_loss_margin).map(specialRowFromV1),
  };
}

export async function loadTeamList(): Promise<unknown> {
  return fetchV1("/api/v1/teams");
}

export async function loadTeamDocument(
  team: string,
  opts: { season?: string | null; threshold?: number } = {},
): Promise<unknown> {
  const threshold = opts.threshold;
  return fetchV1("/api/v1/teams/document", {
    team,
    season: seasonParam(opts.season),
    threshold:
      threshold != null && threshold !== DEFAULT_CLUTCH_THRESHOLD ? threshold : undefined,
  });
}
