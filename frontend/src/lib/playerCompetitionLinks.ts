import { seasonForUrlQuery } from "./api";
import type { PlayerPeriodRow, PlayerSeasonRow } from "../hooks/usePlayer";

export type CompetitionLinkContext = {
  selectedPlayerName: string;
  database: string | null;
};

export function buildCompetitionEventPath(
  row: PlayerSeasonRow,
  ctx: CompetitionLinkContext,
): string | null {
  if (String(row.row_type ?? "").trim() !== "competition" || !row.competition) {
    return null;
  }

  const qs = new URLSearchParams();
  qs.set("season", seasonForUrlQuery(String(row.season ?? "")));

  if (row.is_tournament) {
    qs.set("tournament", String(row.competition));
    const playerForLink = String(row.player_name ?? "").trim() || ctx.selectedPlayerName;
    if (playerForLink) qs.set("player", playerForLink);
  } else {
    qs.set("league", String(row.competition));
    const teamForLink =
      row.team_name ??
      (row.club
        ? `${String(row.club).trim()}${row.team_number ? ` ${row.team_number}` : ""}`.trim()
        : "");
    if (teamForLink) qs.set("team", teamForLink);
    if (ctx.database) qs.set("database", ctx.database);
  }

  const targetPath = row.is_tournament ? "/turnier" : "/liga";
  return `${targetPath}?${qs.toString()}`;
}

export function buildPeriodEventPath(
  row: PlayerPeriodRow,
  ctx: CompetitionLinkContext,
): string | null {
  if (!row.competition) return null;

  const basePath = buildCompetitionEventPath(
    {
      season: row.season,
      competition: row.competition,
      is_tournament: row.is_tournament,
      row_type: "competition",
      club: row.club,
      team_name: row.team_name,
      team_number: row.team_number,
    },
    ctx,
  );
  if (!basePath) return null;

  const [target, query = ""] = basePath.split("?");
  const qs = new URLSearchParams(query);
  if (row.period_number != null && Number.isFinite(row.period_number)) {
    if (row.is_tournament) qs.set("round", String(row.period_number));
    else qs.set("week", String(row.period_number));
  }
  const next = qs.toString();
  return next ? `${target}?${next}` : target;
}
