import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Crown } from "lucide-react";
import { SegmentedControl } from "../../components/SegmentedControl";
import type { Club300HonorPlayer } from "../../lib/club300Analytics";
import { formatClub300Date } from "../../lib/club300Analytics";
import { buildUrl } from "../../lib/api";
import { buildIndividualGameEventPath } from "../../lib/playerCompetitionLinks";
import { formatCompetitionLabel } from "../../lib/competitionDisplayName";
import { homePaletteColorForTopic } from "../../lib/homePalette";
import { Club300Mark } from "./Club300Mark";

type Filter = "all" | "repeaters";

type Props = {
  players: Club300HonorPlayer[];
  database: string | null;
  tournamentAbbreviations?: Record<string, string>;
  t: (key: string, fallback?: string) => string;
};

const accent = homePaletteColorForTopic("club300");

export function Club300HonorBoard({ players, database, tournamentAbbreviations, t }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return players.filter((player) => {
      if (filter === "repeaters" && player.count < 2) return false;
      if (!needle) return true;
      return player.name.toLowerCase().includes(needle);
    });
  }, [players, filter, query]);

  if (!players.length) {
    return (
      <div className="grid min-h-[12rem] place-items-center rounded-sm border border-dashed border-border text-small text-muted">
        {t("ui.club300.tier_empty", "Keine Spieler mit 300ern.")}
      </div>
    );
  }

  return (
    <div className="rounded-sm border border-border bg-surface">
      <div className="flex flex-col gap-3 border-b border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between lg:px-5">
        <SegmentedControl
          ariaLabel={t("ui.club300.honor_filter", "Ehrentafel filtern")}
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: t("ui.club300.honor_all", "Alle") },
            {
              value: "repeaters",
              label: t("ui.club300.honor_repeaters", "Mehrfach"),
            },
          ]}
        />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("ui.club300.honor_search", "Spieler filtern…")}
          className="h-9 w-full rounded-sm border border-border bg-surface-subtle px-2.5 text-small sm:max-w-[16rem]"
        />
      </div>

      {visible.length === 0 ? (
        <p className="px-4 py-6 text-small text-muted lg:px-5">
          {t("ui.club300.honor_none", "Keine Treffer in der Ehrentafel.")}
        </p>
      ) : (
        <ol className="divide-y divide-border">
          {visible.map((player) => {
            const isRecord = player.rank === 1;
            const playerHref = buildUrl("/spieler", {
              player_name: player.name,
              ...(player.playerId ? { player_id: player.playerId } : {}),
            });
            return (
              <li
                key={`${player.playerId || player.name}-${player.rank}`}
                className={isRecord ? "bg-accent-tint/40" : undefined}
              >
                <div className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center lg:px-5">
                  <div className="flex min-w-0 flex-1 items-center gap-3">
                    <span className="w-8 shrink-0 font-mono text-small tabular-nums text-muted">
                      {player.rank}
                    </span>
                    <div className="min-w-0 flex-1">
                      <Link
                        to={playerHref}
                        className="flex items-center gap-1.5 font-medium text-foreground hover:text-accent hover:underline"
                      >
                        <span className="truncate">{player.name}</span>
                        {isRecord ? (
                          <Crown
                            className="h-4 w-4 shrink-0"
                            style={{ color: accent }}
                            strokeWidth={1.75}
                            aria-hidden
                          />
                        ) : null}
                      </Link>
                      <p className="text-caption text-muted mt-0.5 truncate">
                        {t("ui.club300.last_game", "Zuletzt")} {formatClub300Date(player.lastDate)}
                        {player.lastCompetition
                          ? ` · ${formatCompetitionLabel(player.lastCompetition, {
                              isTournament: player.games[0]?.is_tournament === true,
                              tournamentAbbreviations,
                            })}`
                          : ""}
                      </p>
                    </div>
                  </div>
                  <div className="flex min-w-0 items-center justify-between gap-3 sm:justify-end">
                    <div className="flex flex-wrap justify-end gap-1">
                      {player.games.map((game, idx) => {
                        const href = buildIndividualGameEventPath(game, {
                          selectedPlayerName: player.name,
                          database,
                        });
                        const label = [
                          formatClub300Date(game.date),
                          formatCompetitionLabel(String(game.competition ?? ""), {
                            isTournament: !!game.is_tournament,
                            tournamentAbbreviations,
                          }),
                          String(game.season ?? "").trim(),
                        ]
                          .filter((part) => part && part !== "—")
                          .join(" · ");
                        return (
                          <Club300Mark
                            key={`${player.name}-${game.date}-${game.competition}-${idx}`}
                            href={href}
                            title={label}
                          />
                        );
                      })}
                    </div>
                    <span className="w-10 shrink-0 text-right font-mono text-stat-md tabular-nums text-foreground">
                      {player.count}×
                    </span>
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
