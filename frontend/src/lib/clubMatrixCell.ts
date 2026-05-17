export type ClubMatrixCellItem = {
  league: string;
  final_position?: number | null;
  team_count?: number | null;
};

export type ClubMatrixSeasonCell =
  | string
  | {
      leagues?: string;
      items?: ClubMatrixCellItem[];
    };

export function normalizeClubMatrixCell(cell: ClubMatrixSeasonCell | undefined): {
  label: string;
  items: ClubMatrixCellItem[];
} {
  if (cell == null || cell === "") return { label: "", items: [] };
  if (typeof cell === "string") {
    const leagues = cell
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    return {
      label: cell,
      items: leagues.map((league) => ({ league })),
    };
  }
  const items = cell.items ?? [];
  const label =
    cell.leagues ??
    items
      .map((i) => i.league)
      .filter(Boolean)
      .join(", ");
  return { label, items: items.length > 0 ? items : label.split(",").map((s) => ({ league: s.trim() })).filter((i) => i.league) };
}

export function formatMatrixCellItem(item: ClubMatrixCellItem): string {
  const league = item.league;
  const pos = item.final_position;
  const total = item.team_count;
  if (pos != null && pos > 0 && total != null && total > 0) {
    return `${league} (${pos}/${total})`;
  }
  return league;
}
