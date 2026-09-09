import { useMemo } from "react";
import { TopicPageHeader } from "../components/TopicPageHeader";
import { useSearchParams } from "react-router-dom";
import { useMyClub } from "../hooks/useMyClub";
import { useClub300Games } from "../hooks/usePlayer";
import { useTranslations } from "../hooks/useTranslations";
import { EChart } from "../lib/charts/EChart";
import {
  buildClub300BubblePoints,
  buildClub300HonorRoll,
  buildClub300Summary,
  club300BubbleChartOption,
  formatClub300Date,
} from "../lib/club300Analytics";
import { formatCompetitionLabel } from "../lib/competitionDisplayName";
import { homePaletteColorForTopic } from "../lib/homePalette";
import { Club300GameLog } from "./club300/Club300GameLog";
import { Club300GamesTable } from "./club300/Club300GamesTable";
import { Club300HonorBoard } from "./club300/Club300HonorBoard";
import { CollapsibleSection } from "../components/CollapsibleSection";

const accent = homePaletteColorForTopic("club300");

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
  const honor = useMemo(() => buildClub300HonorRoll(games), [games]);
  const summary = useMemo(() => buildClub300Summary(games), [games]);

  const subtitle = clubFilter
    ? t(
        "ui.club300.subtitle_club",
        "Perfekte 300er von Spielern aus {club} (aktiv & Alumni).",
      ).replace("{club}", clubFilter)
    : t(
        "ui.club300.subtitle",
        "Die Ehrentafel der perfekten Spiele — wer wie oft, und jedes einzelne 300er.",
      );

  const emptyMessage = clubFilter
    ? t(
        "ui.club300.empty_club",
        "Keine 300er für Spieler aus {club} in der aktuellen Datenquelle.",
      ).replace("{club}", clubFilter)
    : t("ui.club300.empty", "Keine 300er in der aktuellen Datenquelle.");

  const latestMeta = summary.latest
    ? [
        summary.latest.player_name,
        formatClub300Date(summary.latest.date),
        formatCompetitionLabel(String(summary.latest.competition ?? ""), {
          isTournament: !!summary.latest.is_tournament,
          tournamentAbbreviations,
        }),
      ]
        .filter(Boolean)
        .join(" · ")
    : "—";

  const recordLabel =
    summary.recordHolders.length === 0
      ? "—"
      : summary.recordHolders.length === 1
        ? `${summary.recordCount}× · ${summary.recordHolders[0].name}`
        : t("ui.club300.record_tied", "{n}× · {count} Spieler")
            .replace("{n}", String(summary.recordCount))
            .replace("{count}", String(summary.recordHolders.length));

  return (
    <div className="mx-auto max-w-[1280px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <TopicPageHeader
        topic="club300"
        eyebrow={t("ui.nav.group_start", "Start")}
        className="mb-8"
        title={t("ui.club300.title", "Club 300")}
        description={subtitle}
      />

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
        <div className="space-y-10">
          <section
            className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
            aria-label={t("ui.club300.kpis", "Kennzahlen")}
          >
            <KpiTile
              label={t("ui.club300.kpi_games", "Perfekte Spiele")}
              value={gamesQuery.isPending ? "…" : String(summary.gameCount)}
              hero
            />
            <KpiTile
              label={t("ui.club300.kpi_players", "Mitglieder")}
              value={gamesQuery.isPending ? "…" : String(summary.playerCount)}
            />
            <KpiTile
              label={t("ui.club300.kpi_record", "Rekord")}
              value={gamesQuery.isPending ? "…" : recordLabel}
              compact
            />
            <KpiTile
              label={t("ui.club300.kpi_latest", "Letzter 300er")}
              value={gamesQuery.isPending ? "…" : latestMeta}
              compact
            />
          </section>

          <section>
            <div className="mb-4">
              <p className="text-label uppercase text-muted mb-1.5">
                {t("ui.club300.honor_eyebrow", "Ehrentafel")}
              </p>
              <h2 className="text-h2">{t("ui.club300.honor_title", "Wer hat wie viele 300er?")}</h2>
              <p className="text-small text-muted mt-1 max-w-[72ch]">
                {t(
                  "ui.club300.honor_hint",
                  "Jeder Kasten ist ein perfektes Spiel. Name öffnet die Spielerseite, 300 den Wettbewerb.",
                )}
              </p>
            </div>
            {gamesQuery.isPending ? (
              <div className="h-64 rounded-sm border border-border bg-surface-subtle" />
            ) : (
              <Club300HonorBoard
                players={honor}
                database={databaseParam}
                tournamentAbbreviations={tournamentAbbreviations}
                t={t}
              />
            )}
          </section>

          <section>
            <div className="mb-4">
              <p className="text-label uppercase text-muted mb-1.5">
                {t("ui.club300.table_eyebrow", "Chronik")}
              </p>
              <h2 className="text-h2">{t("ui.club300.log_title", "Jedes 300er, notiert")}</h2>
              <p className="text-small text-muted mt-1 max-w-[72ch]">
                {t(
                  "ui.club300.log_hint",
                  "Neueste zuerst. Spieler und Wettbewerb sind anklickbar.",
                )}
              </p>
            </div>
            {gamesQuery.isPending ? (
              <div className="h-64 rounded-sm border border-border bg-surface-subtle" />
            ) : (
              <Club300GameLog
                games={games}
                database={databaseParam}
                tournamentAbbreviations={tournamentAbbreviations}
                t={t}
              />
            )}
          </section>

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

          <CollapsibleSection
            eyebrow={t("ui.club300.table_sort_eyebrow", "Tabelle")}
            title={t("ui.club300.table_title", "Alle 300er")}
            defaultOpen={false}
            lazyMount
            expandLabel={t("ui.club300.table_expand", "Tabelle einblenden")}
            collapseLabel={t("ui.club300.table_collapse", "Tabelle ausblenden")}
          >
            <p className="text-small text-muted mb-4">
              {t(
                "ui.club300.table_hint",
                "Sortierbar nach Spieler, Wettbewerb, Saison, Ligaebene und Datum.",
              )}
            </p>
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
          </CollapsibleSection>
        </div>
      )}
    </div>
  );
}

function KpiTile({
  label,
  value,
  hero = false,
  compact = false,
}: {
  label: string;
  value: string;
  hero?: boolean;
  compact?: boolean;
}) {
  return (
    <div
      className="rounded-sm border border-border bg-surface px-4 py-3"
      style={hero ? { borderTopWidth: 3, borderTopColor: accent } : undefined}
    >
      <p className="text-label uppercase text-muted">{label}</p>
      <p
        className={
          compact
            ? "mt-1 truncate text-body font-medium text-foreground"
            : "mt-1 font-mono text-stat-lg tabular-nums text-foreground"
        }
        title={value}
      >
        {value}
      </p>
    </div>
  );
}
