import type { ClubMatrixRow } from "../hooks/useLeague";
import type { TeamHistory } from "../hooks/useTeam";
import { normalizeClubMatrixCell } from "./clubMatrixCell";
import { getLeagueLevel } from "./leagueLevel";

/** Build chart/history shape from club-matrix row (same source as Liga-Zuordnung table). */
export function historyFromMatrixRow(
  row: ClubMatrixRow,
  matrixSeasons: string[],
): TeamHistory {
  const history: TeamHistory = {};
  const seasonsByYear = row.seasons ?? {};
  for (const season of matrixSeasons) {
    const { items } = normalizeClubMatrixCell(seasonsByYear[season]);
    const item =
      items.find((i) => i.final_position != null && i.final_position > 0) ?? items[0];
    if (!item?.league) continue;
    const pos = item.final_position;
    if (pos == null || pos <= 0) continue;
    history[season] = {
      league_name: item.league,
      final_position: pos,
      league_level: item.league_level ?? getLeagueLevel(item.league),
    };
  }
  return history;
}
