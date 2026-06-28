import { Link } from "react-router-dom";
import { Crown } from "lucide-react";
import type { Club300PlayerTier } from "../../lib/club300Analytics";
import { getPaletteColor } from "../../lib/color-utils";
import { buildUrl } from "../../lib/api";

type Props = {
  tiers: Club300PlayerTier[];
  totalPlayers: number;
  t: (key: string, fallback?: string) => string;
};

/**
 * Tiered “staircase” view: players grouped by identical 300 counts, ordered
 * from most perfect games at the top to fewest at the bottom.
 */
export function Club300TierLadder({ tiers, totalPlayers, t }: Props) {
  if (!tiers.length) {
    return (
      <div className="grid h-[280px] place-items-center rounded-sm border border-dashed border-border text-small text-muted">
        {t("ui.club300.tier_empty", "Keine Spieler mit 300ern.")}
      </div>
    );
  }

  const maxCount = tiers[0]?.count ?? 1;

  return (
    <div className="rounded-sm border border-border bg-surface p-4 lg:p-5">
      <ol className="relative space-y-3">
        {tiers.map((tier, tierIdx) => {
          const widthPct = Math.max(28, Math.round((tier.count / maxCount) * 100));
          const accent = getPaletteColor(tierIdx);
          const isTop = tierIdx === 0;
          const rankLabel =
            tier.playersAhead === 0
              ? t("ui.club300.tier_leader", "Spitzenreiter")
              : t("ui.club300.tier_ahead", "vor {n} Spielern").replace(
                  "{n}",
                  String(tier.playersAhead),
                );

          return (
            <li key={tier.count} className="relative">
              <div
                className="overflow-hidden rounded-sm border border-border bg-surface-subtle/60"
                style={{
                  marginLeft: `${Math.min(tierIdx * 8, 40)}px`,
                  borderLeftWidth: 4,
                  borderLeftColor: accent,
                }}
              >
                <div
                  className="h-1"
                  style={{
                    width: `${widthPct}%`,
                    backgroundColor: `color-mix(in srgb, ${accent} 55%, transparent)`,
                  }}
                  aria-hidden
                />
                <div className="flex flex-col gap-3 p-3 sm:flex-row sm:items-center">
                <div className="flex shrink-0 items-center gap-2.5 sm:w-32">
                  <span
                    className="grid h-8 w-8 shrink-0 place-items-center rounded-full font-mono text-small font-semibold tabular-nums text-white"
                    style={{ backgroundColor: accent }}
                    aria-hidden
                  >
                    {tier.count}
                  </span>
                  <div>
                    <p className="flex items-center gap-1.5 font-mono text-h3 font-semibold tabular-nums leading-none text-foreground">
                      {tier.count}×
                      {isTop ? (
                        <Crown
                          className="h-4 w-4 shrink-0"
                          style={{ color: accent }}
                          strokeWidth={1.75}
                          aria-hidden
                        />
                      ) : null}
                    </p>
                    <p className="text-label text-muted mt-1">{rankLabel}</p>
                  </div>
                </div>

                <div className="min-w-0 flex-1">
                  <p className="text-label text-muted mb-2">
                    {tier.players.length === 1
                      ? t("ui.club300.one_player", "1 Spieler")
                      : t("ui.club300.n_players", "{n} Spieler").replace(
                          "{n}",
                          String(tier.players.length),
                        )}
                    {totalPlayers > 0
                      ? ` · ${Math.round((tier.players.length / totalPlayers) * 100)}%`
                      : ""}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {tier.players.map((player) => (
                      <Link
                        key={`${tier.count}-${player.name}`}
                        to={buildUrl("/spieler", {
                          player_name: player.name,
                          ...(player.playerId ? { player_id: player.playerId } : {}),
                        })}
                        className="inline-flex max-w-full items-center rounded-sm border border-border bg-surface px-2 py-1 text-small text-foreground hover:border-accent hover:text-accent"
                        title={player.name}
                      >
                        <span className="truncate">{player.name}</span>
                      </Link>
                    ))}
                  </div>
                </div>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
