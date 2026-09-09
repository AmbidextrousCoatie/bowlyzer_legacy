import { useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { CollapsibleSection } from "../../../components/CollapsibleSection";
import { useAppLink } from "../../../hooks/useAppLink";
import { useSeasonTimetables, type LeagueOption } from "../../../hooks/useLeague";
import { useTranslations } from "../../../hooks/useTranslations";
import { EChart } from "../../../lib/charts/EChart";
import { TEAM_COLOR_PALETTES } from "../../../lib/color-utils";
import {
  spielplanChartHeight,
  spielplanChartOption,
  spielplanPointFromEvent,
} from "../../../lib/spielplanChart";
import { buildSpielplanChartModel } from "../../../lib/seasonSpielplan";

const VENUE_PALETTE = [
  ...TEAM_COLOR_PALETTES.rainbowPastel,
  ...TEAM_COLOR_PALETTES.harmonic10,
] as const;

type Props = {
  season: string;
  leagues: LeagueOption[];
  leaguesLoading: boolean;
};

export function SeasonSpielplan({ season, leagues, leaguesLoading }: Props) {
  const { t, language } = useTranslations();
  const navigate = useNavigate();
  const linkTo = useAppLink();
  const lang = language === "en" ? "en" : "de";
  const leagueValues = useMemo(() => leagues.map((league) => league.value), [leagues]);
  const queries = useSeasonTimetables(season, leagueValues, !leaguesLoading);
  const pending = leaguesLoading || queries.some((query) => query.isPending);
  const errorCount = queries.filter((query) => query.isError).length;
  const model = useMemo(
    () =>
      buildSpielplanChartModel(
        leagues,
        queries.map((query) => query.data),
        lang,
        VENUE_PALETTE,
      ),
    [leagues, queries, lang],
  );
  const option = useMemo(() => spielplanChartOption(model, t, lang), [model, t, lang]);

  const onPointClick = useCallback(
    (data: unknown) => {
      const point = spielplanPointFromEvent(data);
      if (!point) return;
      void navigate(linkTo("/liga", { season, league: point.league, week: point.week }));
    },
    [linkTo, navigate, season],
  );

  return (
    <CollapsibleSection
      title={t("match_schedule", "Spielplan")}
      defaultOpen
      expandLabel={t("ui.league.spielplan_expand", "Spielplan einblenden")}
      collapseLabel={t("ui.league.spielplan_collapse", "Spielplan ausblenden")}
    >
      <p className="text-small text-muted mb-4">
        {t(
          "ui.league.spielplan_hint",
          "Eine Zeile je Liga, die Farbe ist die Halle. Gleiche Spalte = gleicher Tag.",
        )}
      </p>
      {pending ? (
        <div aria-busy="true">
          <span className="sr-only">{t("status.loading", "Lade Daten…")}</span>
          <SpielplanSkeleton />
        </div>
      ) : !option ? (
        <p className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
          {t("ui.league.spielplan_empty", "Keine Termine für diese Auswahl.")}
        </p>
      ) : (
        <div className="space-y-4">
          {errorCount > 0 && (
            <p className="text-small text-danger-fg">
              {t("ui.league.spielplan_partial_error", "Einige Ligen konnten nicht geladen werden.")}
            </p>
          )}
          <div className="overflow-x-auto">
            <div style={{ minWidth: Math.max(640, 112 + model.dateKeys.length * 56) }}>
              <EChart
                option={option}
                height={spielplanChartHeight(model.leagueLabels.length)}
                onPointClick={onPointClick}
              />
            </div>
          </div>
          <ul className="flex flex-wrap gap-x-4 gap-y-2">
            {model.venues.map((venue) => (
              <li key={venue.venueKey} className="flex items-center gap-2 text-small">
                <span
                  className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ backgroundColor: venue.color }}
                  aria-hidden
                />
                <span className="font-mono text-caption text-foreground">{venue.abbrev}</span>
                <span className="text-muted">= {venue.displayName}</span>
              </li>
            ))}
          </ul>
          {model.undated.length > 0 && (
            <p className="text-small text-muted">
              {t("ui.league.spielplan_undated", "Ohne Datum")}:{" "}
              {model.undated.map((event) => `${event.leagueShort} · ${event.week}`).join(", ")}
            </p>
          )}
        </div>
      )}
    </CollapsibleSection>
  );
}

function SpielplanSkeleton() {
  return (
    <div className="space-y-4" aria-hidden>
      <div className="h-[320px] rounded-sm bg-surface-subtle" />
      <div className="h-4 w-2/3 rounded-xs bg-surface-subtle" />
    </div>
  );
}
