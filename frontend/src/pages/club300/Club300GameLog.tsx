import { Link } from "react-router-dom";
import type { IndividualGameRecord } from "../../hooks/usePlayer";
import { buildUrl } from "../../lib/api";
import { formatClub300Date } from "../../lib/club300Analytics";
import { formatCompetitionLabel } from "../../lib/competitionDisplayName";
import { buildIndividualGameEventPath } from "../../lib/playerCompetitionLinks";
import { Club300Mark } from "./Club300Mark";

type Props = {
  games: IndividualGameRecord[];
  database: string | null;
  tournamentAbbreviations?: Record<string, string>;
  t: (key: string, fallback?: string) => string;
};

export function Club300GameLog({ games, database, tournamentAbbreviations, t }: Props) {
  if (!games.length) {
    return (
      <div className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
        {t("ui.club300.empty", "Keine 300er in der aktuellen Datenquelle.")}
      </div>
    );
  }

  return (
    <ol className="divide-y divide-border rounded-sm border border-border bg-surface">
      {games.map((game, idx) => {
        const name = String(game.player_name ?? "").trim() || "—";
        const playerHref = game.player_name
          ? buildUrl("/spieler", {
              player_name: game.player_name,
              ...(game.player_id ? { player_id: game.player_id } : {}),
            })
          : null;
        const eventHref = buildIndividualGameEventPath(game, {
          selectedPlayerName: name,
          database,
        });
        const competition = formatCompetitionLabel(String(game.competition ?? ""), {
          isTournament: !!game.is_tournament,
          tournamentAbbreviations,
        });
        const season = String(game.season ?? "").trim();
        const meta = [competition, season, game.club].filter(Boolean).join(" · ");

        return (
          <li
            key={`${game.player_id || name}-${game.date}-${game.competition}-${idx}`}
            className="flex items-center gap-3 px-4 py-2.5 lg:px-5"
          >
            <time className="w-[6.5rem] shrink-0 font-mono text-caption tabular-nums text-muted">
              {formatClub300Date(game.date)}
            </time>
            <div className="min-w-0 flex-1">
              {playerHref ? (
                <Link
                  to={playerHref}
                  className="block truncate font-medium text-foreground hover:text-accent hover:underline"
                >
                  {name}
                </Link>
              ) : (
                <p className="truncate font-medium">{name}</p>
              )}
              {eventHref ? (
                <Link
                  to={eventHref}
                  className="mt-0.5 block truncate text-caption text-muted hover:text-accent"
                >
                  {meta || "—"}
                </Link>
              ) : (
                <p className="mt-0.5 truncate text-caption text-muted">{meta || "—"}</p>
              )}
            </div>
            <Club300Mark href={eventHref} title={meta} size="md" />
          </li>
        );
      })}
    </ol>
  );
}
