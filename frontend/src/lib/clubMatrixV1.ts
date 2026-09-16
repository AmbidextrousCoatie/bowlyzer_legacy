import type { ClubMatrixPayload, ClubMatrixRow } from "../hooks/useLeague";
import { normalizeClubMatrixCell } from "./clubMatrixCell";
import { fetchV1 } from "./v1";

export type ClubHistoryDocument = {
  club: string;
  seasons: string[];
  rows: ClubMatrixRow[];
};

export type ClubListDocument = {
  clubs: string[];
};

function leagueLongNamesFromRows(rows: ClubMatrixRow[]): Record<string, string> {
  const names: Record<string, string> = {};
  for (const row of rows) {
    for (const cell of Object.values(row.seasons ?? {})) {
      for (const item of normalizeClubMatrixCell(cell).items) {
        const league = String(item.league ?? "").trim();
        if (league) names[league] = league;
      }
    }
  }
  return names;
}

/** Map v1 club list + history onto the Flask club-matrix payload the SPA already consumes. */
export function clubMatrixFromV1(args: {
  clubs: string[];
  history?: ClubHistoryDocument | null;
  onlyUnnumbered: boolean;
  selectedClub: string;
}): ClubMatrixPayload {
  const selected = (args.history?.club || args.selectedClub).trim();
  const rows = args.history?.rows ?? [];
  return {
    clubs: args.clubs,
    selected_club: selected,
    only_unnumbered: args.onlyUnnumbered,
    matrix: {
      club: selected,
      seasons: args.history?.seasons ?? [],
      rows,
    },
    league_long_names: leagueLongNamesFromRows(rows),
  };
}

export async function loadClubMatrix(
  club: string | null,
  onlyUnnumbered: boolean,
): Promise<ClubMatrixPayload> {
  const selected = (club ?? "").trim();
  const list = fetchV1<ClubListDocument>("/api/v1/clubs", {
    unnumbered: onlyUnnumbered || undefined,
  });
  if (!selected) {
    const clubs = await list;
    return clubMatrixFromV1({
      clubs: clubs.clubs ?? [],
      onlyUnnumbered,
      selectedClub: "",
    });
  }
  const [clubs, history] = await Promise.all([
    list,
    fetchV1<ClubHistoryDocument>("/api/v1/clubs/history", { club: selected }),
  ]);
  return clubMatrixFromV1({
    clubs: clubs.clubs ?? [],
    history,
    onlyUnnumbered,
    selectedClub: selected,
  });
}
