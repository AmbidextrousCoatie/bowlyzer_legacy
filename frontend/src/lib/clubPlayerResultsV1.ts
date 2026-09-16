import type { ClubPlayerResultsPayload } from "../hooks/useLeague";
import type { ColumnGroup, TableData } from "./datatable/types";
import { TEAM_COLOR_PALETTES } from "./color-utils";
import { fetchV1 } from "./v1";

const ACTIVE_ACCENT = TEAM_COLOR_PALETTES.rainbowPastel[2];
const ALUMNI_ACCENT = TEAM_COLOR_PALETTES.rainbowPastel[5];

export type ClubPlayerResult = {
  rank: number;
  player_id: string;
  player_name: string;
  games: number;
  average: number | null;
  best_season: string | null;
  best_season_average: number | null;
  membership_seasons: number;
  club_active: boolean;
};

function optStr(value: unknown): string | null {
  if (value == null || value === "") return null;
  return String(value);
}

function optNum(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function playerFromV1(raw: Record<string, unknown>, index: number): ClubPlayerResult | null {
  const playerName = optStr(raw.player_name ?? raw.player);
  if (!playerName) return null;
  return {
    rank: optNum(raw.rank) ?? index,
    player_id: optStr(raw.player_id) ?? "",
    player_name: playerName,
    games: optNum(raw.games) ?? 0,
    average: optNum(raw.average),
    best_season: optStr(raw.best_season),
    best_season_average: optNum(raw.best_season_average),
    membership_seasons: optNum(raw.membership_seasons ?? raw.seasons) ?? 0,
    club_active: Boolean(raw.club_active),
  };
}

function playerColumns(): ColumnGroup[] {
  return [
    {
      title: "Spieler",
      title_key: "ui.team.club_player_group",
      frozen: "left",
      columns: [
        {
          title: "Platz",
          title_key: "position",
          field: "rank",
          width: "60px",
          align: "center",
          decimal_places: 0,
        },
        {
          title: "Spieler",
          title_key: "player",
          field: "player_name",
          width: "120px",
          align: "left",
        },
        {
          title: "ID",
          title_key: "ui.team.player_id_col",
          field: "player_id",
          width: "80px",
          align: "left",
        },
      ],
    },
    {
      title: "Gesamt",
      title_key: "ui.team.club_alltime_group",
      columns: [
        {
          title: "Schnitt",
          title_key: "ui.player.average_col",
          field: "average",
          width: "70px",
          align: "center",
          decimal_places: 2,
        },
        {
          title: "Spiele",
          title_key: "ui.player.games",
          field: "games",
          width: "70px",
          align: "center",
          decimal_places: 0,
        },
      ],
    },
    {
      title: "Beste Saison",
      title_key: "ui.team.club_best_season_group",
      columns: [
        {
          title: "Saison",
          title_key: "season",
          field: "best_season",
          width: "90px",
          align: "center",
        },
        {
          title: "Schnitt",
          title_key: "ui.player.average_col",
          field: "best_season_average",
          width: "70px",
          align: "center",
          decimal_places: 2,
        },
      ],
    },
    {
      title: "Zugehörigkeit",
      title_key: "ui.team.club_membership_group",
      columns: [
        {
          title: "Saisons",
          title_key: "ui.team.club_membership_years",
          field: "membership_seasons",
          width: "70px",
          align: "center",
          decimal_places: 0,
        },
      ],
    },
  ];
}

export function clubPlayerResultsFromV1(raw: Record<string, unknown>): ClubPlayerResultsPayload {
  const players = Array.isArray(raw.players) ? raw.players : [];
  const rows = players
    .filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object")
    .map((row, index) => playerFromV1(row, index + 1))
    .filter((row): row is ClubPlayerResult => row != null);

  const table: TableData = {
    columns: playerColumns(),
    data: rows,
    row_metadata: rows.map((row) => ({
      rowAccentColor: row.club_active ? ACTIVE_ACCENT : ALUMNI_ACCENT,
    })),
    default_sort: { field: "average", dir: "desc" },
    metadata: {
      kind: "club_player_results",
      latest_season: optStr(raw.latest_season),
    },
  };
  return { club: String(raw.club ?? ""), table };
}

export async function loadClubPlayerResults(
  club: string,
  season?: string | null,
): Promise<ClubPlayerResultsPayload> {
  const raw = await fetchV1<Record<string, unknown>>("/api/v1/clubs/players", {
    club,
    season: season || undefined,
  });
  return clubPlayerResultsFromV1(raw);
}
