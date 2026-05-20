import type { PlayerLifetimeStats } from "../../../hooks/usePlayer";

type Props = {
  stats: PlayerLifetimeStats | null | undefined;
  /** EDV player id from the URL / search, shown in Gesamtwerte block. */
  playerId?: string;
  t: (key: string, fallback?: string) => string;
};

export function LifetimeStats({ stats, playerId, t }: Props) {
  const totalGames = stats?.total_games ?? null;
  const totalPins = stats?.total_pins ?? null;
  const avg = stats?.average_score ?? null;
  const bestGame = stats?.best_game ?? null;
  const bestSeason = stats?.best_season ?? null;
  const mostImproved = stats?.most_improved ?? null;

  return (
    <section>
      <div className="mb-4">
        <p className="text-label uppercase text-muted mb-1.5">
          {t("ui.player.lifetime_title", "Karrierestatistik")}
        </p>
        <h2 className="text-h2">{t("ui.player.overall_stats", "Gesamtwerte")}</h2>
      </div>

      <div className="grid grid-cols-1 gap-x-12 gap-y-8 md:grid-cols-3">
        <StatGroup label={t("ui.player.career_aggregate", "Karrierewerte")}>
          {playerId ? (
            <StatRow
              label={t("ui.player.edv_id", "EDV-ID")}
              value={playerId}
              mono={true}
            />
          ) : null}
          <StatRow
            label={t("ui.player.total_games", "Spiele gesamt")}
            value={formatInt(totalGames)}
          />
          <StatRow
            label={t("ui.player.total_pins", "Pins gesamt")}
            value={formatInt(totalPins, true)}
          />
          <StatRow
            label={t("ui.player.average_score", "Durchschnitt")}
            value={formatDecimal(avg, 2)}
          />
        </StatGroup>

        <StatGroup label={t("ui.player.best_performance", "Bestleistungen")}>
          <StatRow
            label={t("ui.player.highest_game", "Höchstes Spiel")}
            value={formatInt(bestGame?.score ?? null)}
          />
          <StatRow
            label={t("ui.player.event", "Event")}
            value={bestGame?.event ?? "—"}
            mono={false}
          />
          <StatRow label={t("ui.player.date", "Datum")} value={bestGame?.date ?? "—"} />
        </StatGroup>

        <StatGroup label={t("ui.player.season_records", "Saisonrekorde")}>
          <StatRow
            label={t("ui.player.best_season", "Beste Saison")}
            value={
              bestSeason?.season
                ? `${bestSeason.season} (${formatDecimal(bestSeason.average ?? null, 2)})`
                : "—"
            }
            mono={false}
          />
          <StatRow
            label={t("ui.player.most_improved", "Größter Sprung")}
            value={
              mostImproved?.season && mostImproved.improvement != null
                ? `${mostImproved.season} (+${formatDecimal(mostImproved.improvement, 2)})`
                : "—"
            }
            mono={false}
          />
        </StatGroup>
      </div>
    </section>
  );
}

function StatGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-label uppercase text-subtle mb-3">{label}</p>
      <dl className="space-y-2">{children}</dl>
    </div>
  );
}

function StatRow({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between border-b border-border pb-1.5">
      <dt className="text-small text-muted">{label}</dt>
      <dd
        className={
          "text-body text-foreground font-semibold " + (mono ? "font-mono tabular-nums" : "")
        }
      >
        {value}
      </dd>
    </div>
  );
}

function formatInt(value: number | string | null | undefined, useGrouping = false): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return String(value);
  return useGrouping ? n.toLocaleString("de-DE") : String(Math.trunc(n));
}

function formatDecimal(value: number | null | undefined, decimals: number): string {
  if (value === null || value === undefined) return "—";
  if (!Number.isFinite(value)) return "—";
  return value.toFixed(decimals);
}
