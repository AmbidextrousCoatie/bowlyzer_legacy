import { useMemo } from "react";
import { Star } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useMyClub } from "../hooks/useMyClub";
import { useClub300Games } from "../hooks/usePlayer";
import { useTranslations } from "../hooks/useTranslations";
import { EChart } from "../lib/charts/EChart";
import {
  buildClub300BubblePoints,
  buildClub300PlayerTiers,
  club300BubbleChartOption,
} from "../lib/club300Analytics";
import { Club300GamesTable } from "./club300/Club300GamesTable";
import { Club300TierLadder } from "./club300/Club300TierLadder";

export function Club300() {
  const { t, tournamentAbbreviations } = useTranslations();
  const [searchParams] = useSearchParams();
  const databaseParam = searchParams.get("database");
  const { active: myClubActive, resolvedClub, myClub } = useMyClub();
  const clubFilter = myClubActive ? resolvedClub || myClub || null : null;
  const gamesQuery = useClub300Games(clubFilter);
  const games = gamesQuery.data ?? [];

  const bubble = useMemo(() => buildClub300BubblePoints(games), [games]);
  const bubbleOption = useMemo(
    () => club300BubbleChartOption(bubble.seasons, bubble.levelOrder, bubble.points),
    [bubble],
  );
  const tiers = useMemo(() => buildClub300PlayerTiers(games), [games]);
  const totalPlayers = useMemo(
    () => tiers.reduce((sum, tier) => sum + tier.players.length, 0),
    [tiers],
  );

  const subtitle = clubFilter
    ? t(
        "ui.club300.subtitle_club",
        "Perfekte 300er von Spielern aus {club} (aktiv & Alumni).",
      ).replace("{club}", clubFilter)
    : t("ui.club300.subtitle", "Alle perfekten 300er in der Datenquelle — neueste zuerst.");

  const emptyMessage = clubFilter
    ? t(
        "ui.club300.empty_club",
        "Keine 300er für Spieler aus {club} in der aktuellen Datenquelle.",
      ).replace("{club}", clubFilter)
    : t("ui.club300.empty", "Keine 300er in der aktuellen Datenquelle.");

  return (
    <div className="mx-auto max-w-[1280px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <header className="mb-10">
        <p className="text-label uppercase text-muted mb-2">{t("ui.nav.group_start", "Start")}</p>
        <div className="flex items-start gap-3">
          <Star className="mt-1 h-7 w-7 shrink-0 text-accent" strokeWidth={1.75} aria-hidden />
          <div>
            <h1 className="text-h1">{t("ui.club300.title", "Club 300")}</h1>
            <p className="text-body text-muted mt-2 max-w-[72ch]">{subtitle}</p>
          </div>
        </div>
      </header>

      {gamesQuery.isError && (
        <section className="mb-8 rounded-sm border border-danger-fg/40 bg-surface p-6 text-small text-danger-fg">
          {gamesQuery.error instanceof Error
            ? gamesQuery.error.message
            : t("error_generic", "Fehler beim Laden")}
        </section>
      )}

      {gamesQuery.isSuccess && games.length === 0 && (
        <section className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
          {emptyMessage}
        </section>
      )}

      {(gamesQuery.isPending || games.length > 0) && (
        <div className="space-y-12">
          <div className="grid grid-cols-1 gap-8 xl:grid-cols-2">
            <section>
              <div className="mb-4">
                <p className="text-label uppercase text-muted mb-1.5">
                  {t("ui.club300.bubble_eyebrow", "Verteilung")}
                </p>
                <h2 className="text-h2">
                  {t("ui.club300.bubble_title", "300er nach Saison & Ligaebene")}
                </h2>
                <p className="text-small text-muted mt-1">
                  {t(
                    "ui.club300.bubble_hint",
                    "Kreisgröße = Anzahl perfekter Spiele in Saison und Liga-Stufe.",
                  )}
                </p>
              </div>
              {gamesQuery.isPending ? (
                <div className="h-[320px] rounded-sm border border-border bg-surface-subtle" />
              ) : bubbleOption ? (
                <div className="rounded-sm border border-border bg-surface p-3">
                  <EChart option={bubbleOption} height={320} />
                </div>
              ) : (
                <div className="grid h-[320px] place-items-center rounded-sm border border-dashed border-border text-small text-muted">
                  {t("ui.club300.bubble_empty", "Keine Daten für die Grafik.")}
                </div>
              )}
            </section>

            <section>
              <div className="mb-4">
                <p className="text-label uppercase text-muted mb-1.5">
                  {t("ui.club300.tier_eyebrow", "Rangliste")}
                </p>
                <h2 className="text-h2">
                  {t("ui.club300.tier_title", "300er-Treppen — wer hat wie viele?")}
                </h2>
                <p className="text-small text-muted mt-1">
                  {t(
                    "ui.club300.tier_hint",
                    "Spieler mit gleicher Anzahl stehen auf einer Stufe — höhere Stufen sind seltener.",
                  )}
                </p>
              </div>
              {gamesQuery.isPending ? (
                <div className="h-[320px] rounded-sm border border-border bg-surface-subtle" />
              ) : (
                <Club300TierLadder tiers={tiers} totalPlayers={totalPlayers} t={t} />
              )}
            </section>
          </div>

          <section>
            <div className="mb-4">
              <p className="text-label uppercase text-muted mb-1.5">
                {t("ui.club300.table_eyebrow", "Chronik")}
              </p>
              <h2 className="text-h2">{t("ui.club300.table_title", "Alle 300er")}</h2>
              <p className="text-small text-muted mt-1">
                {t(
                  "ui.club300.table_hint",
                  "Zeile anklicken für den Wettbewerb — sortierbar wie in der Liga-Ansicht.",
                )}
              </p>
            </div>
            {gamesQuery.isPending ? (
              <div className="h-48 rounded-sm border border-border bg-surface-subtle" />
            ) : (
              <Club300GamesTable
                games={games}
                database={databaseParam}
                tournamentAbbreviations={tournamentAbbreviations}
                t={t}
              />
            )}
          </section>
        </div>
      )}
    </div>
  );
}
