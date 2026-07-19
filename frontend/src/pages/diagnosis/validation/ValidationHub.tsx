import { Link, useSearchParams } from "react-router-dom";
import { useLeagueStandingsValidation } from "../../../hooks/useLeagueStandingsValidation";
import { useClubNameValidation } from "../../../hooks/useClubNameValidation";
import { useTranslations } from "../../../hooks/useTranslations";
import { querySuffixForPath } from "../../../lib/navigationQuery";
import { LEAGUE_STATUS_KEYS, STATUS_CLASS, TOURNAMENT_STATUS_KEYS } from "./validationUi";
const LEAGUE_LABEL: Record<string, string> = {
  perfect: "Perfekt",
  corrected: "Korrigiert",
  yellow: "Gelb",
  red: "Rot",
  skipped: "Übersprungen",
};

const TOURNAMENT_LABEL: Record<string, string> = {
  green: "Grün",
  yellow: "Gelb",
  red: "Rot",
};

export function ValidationHub() {
  const { t } = useTranslations();
  const [searchParams] = useSearchParams();
  const query = useLeagueStandingsValidation();
  const clubQuery = useClubNameValidation();
  const leagueSummary = query.data?.summary;
  const tournamentSummary = query.data?.tournament_quality?.summary;
  const clubSummary = clubQuery.data?.summary;  const querySuffix = querySuffixForPath("/diagnose/validierung", searchParams);

  return (
    <div className="w-full min-w-0 px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <header className="mb-8 lg:mb-10">
        <p className="text-label uppercase text-muted mb-2">
          {t("ui.diagnosis.eyebrow", "Diagnose")}
        </p>
        <h1 className="text-h1">
          {t("ui.diagnosis.validation_hub_title", "Validierung")}
        </h1>
        <p className="text-body text-muted mt-2 max-w-[72ch]">
          {t(
            "ui.diagnosis.validation_hub_desc",
            "Überblick über Liga- und Turnier-Datenqualität nach dem Publish-Lauf.",
          )}
        </p>
      </header>

      {query.isLoading && (
        <p className="text-body text-muted">{t("ui.common.loading", "Laden…")}</p>
      )}
      {query.isError && (
        <p className="text-body text-rose-600">
          {t("ui.diagnosis.standings_validation_error", "Validierung konnte nicht geladen werden.")}
        </p>
      )}

      {query.data && (
        <div className="grid gap-6 lg:grid-cols-2 xl:grid-cols-3">          <section className="rounded-sm border border-border bg-surface">
            <div className="border-b border-border px-5 py-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-h3">{t("league", "Liga")}</h2>
                <p className="text-small text-muted mt-1">
                  {t(
                    "ui.diagnosis.validation_league_blurb",
                    "Excel-Tabellenstand gegen Merge-Daten",
                  )}
                </p>
              </div>
              <Link
                to={`/diagnose/validierung/liga${querySuffix}`}
                className="text-body text-primary underline-offset-2 hover:underline whitespace-nowrap"
              >
                {t("ui.diagnosis.validation_open_detail", "Details →")}
              </Link>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 p-5">
              {LEAGUE_STATUS_KEYS.map((key) => (
                <div key={key} className="rounded-sm border border-border px-4 py-3">
                  <p className="text-label uppercase text-muted">
                    {t(`ui.diagnosis.standings_kpi_${key}`, LEAGUE_LABEL[key])}
                  </p>
                  <p className={`text-h3 mt-1 tabular-nums ${STATUS_CLASS[key] ?? ""}`}>
                    {leagueSummary?.[key] ?? 0}
                  </p>
                </div>
              ))}
            </div>
            <p className="px-5 pb-4 text-caption text-muted">
              {query.data.row_count} {t("ui.diagnosis.standings_rows", "Zeilen")} ·{" "}
              {t("ui.diagnosis.standings_kpi_source", "Quelle")}: {query.data.source}
            </p>
          </section>

          <section className="rounded-sm border border-border bg-surface">
            <div className="border-b border-border px-5 py-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-h3">{t("ui.tournament.tournament", "Turnier")}</h2>
                <p className="text-small text-muted mt-1">
                  {t(
                    "ui.diagnosis.validation_tournament_blurb",
                    "Spieler-ID, Name und Verein je Turnier",
                  )}
                </p>
              </div>
              <Link
                to={`/diagnose/validierung/turniere${querySuffix}`}
                className="text-body text-primary underline-offset-2 hover:underline whitespace-nowrap"
              >
                {t("ui.diagnosis.validation_open_detail", "Details →")}
              </Link>
            </div>
            <div className="grid grid-cols-3 gap-3 p-5">
              {TOURNAMENT_STATUS_KEYS.map((key) => (
                <div key={key} className="rounded-sm border border-border px-4 py-3">
                  <p className="text-label uppercase text-muted">
                    {t(`ui.diagnosis.tournament_kpi_${key}`, TOURNAMENT_LABEL[key])}
                  </p>
                  <p className={`text-h3 mt-1 tabular-nums ${STATUS_CLASS[key] ?? ""}`}>
                    {tournamentSummary?.[key] ?? 0}
                  </p>
                </div>
              ))}
            </div>
            <p className="px-5 pb-4 text-caption text-muted">
              {query.data.tournament_quality?.row_count ?? 0}{" "}
              {t("ui.diagnosis.tournament_kpi_events", "Turniere")} ·{" "}
              {t("ui.diagnosis.standings_kpi_source", "Quelle")}:{" "}
              {query.data.tournament_quality?.source ?? "absent"}
            </p>
          </section>

          <section className="rounded-sm border border-border bg-surface">
            <div className="border-b border-border px-5 py-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-h3">{t("ui.diagnosis.club_mapping_title", "Club-Zuordnung")}</h2>
                <p className="text-small text-muted mt-1">
                  {t(
                    "ui.diagnosis.validation_club_blurb",
                    "Unzugeordnete Turnier-Clubs → kanonischer Club",
                  )}
                </p>
              </div>
              <Link
                to={`/diagnose/validierung/clubs${querySuffix}`}
                className="text-body text-primary underline-offset-2 hover:underline whitespace-nowrap"
              >
                {t("ui.diagnosis.validation_open_detail", "Details →")}
              </Link>
            </div>
            <div className="grid grid-cols-3 gap-3 p-5">
              <div className="rounded-sm border border-border px-4 py-3">
                <p className="text-label uppercase text-muted">
                  {t("ui.diagnosis.club_mapping_kpi_unresolved", "Unzugeordnet")}
                </p>
                <p className="text-h3 mt-1 tabular-nums text-amber-700 dark:text-amber-400">
                  {clubSummary?.unresolved ?? (clubQuery.isLoading ? "…" : 0)}
                </p>
              </div>
              <div className="rounded-sm border border-border px-4 py-3">
                <p className="text-label uppercase text-muted">
                  {t("ui.diagnosis.club_mapping_kpi_proposal", "Mit Vorschlag")}
                </p>
                <p className="text-h3 mt-1 tabular-nums">
                  {clubSummary?.with_proposal ?? (clubQuery.isLoading ? "…" : 0)}
                </p>
              </div>
              <div className="rounded-sm border border-border px-4 py-3">
                <p className="text-label uppercase text-muted">
                  {t("ui.diagnosis.club_mapping_kpi_saved", "Gespeichert")}
                </p>
                <p className="text-h3 mt-1 tabular-nums text-emerald-700 dark:text-emerald-400">
                  {clubQuery.data?.saved_mapping.row_count ?? (clubQuery.isLoading ? "…" : 0)}
                </p>
              </div>
            </div>
            <p className="px-5 pb-4 text-caption text-muted">
              {clubQuery.data?.row_count ?? 0}{" "}
              {t("ui.diagnosis.standings_rows", "Zeilen")} ·{" "}
              {t("ui.diagnosis.standings_kpi_source", "Quelle")}:{" "}
              {clubQuery.data?.source ?? "absent"}
            </p>
          </section>
        </div>
      )}
      <p className="mt-8 text-small text-muted">
        <Link
          to={`/diagnose/datenpipeline${querySuffixForPath("/diagnose/datenpipeline", searchParams)}`}
          className="text-primary underline-offset-2 hover:underline"
        >
          {t("ui.diagnosis.pipeline_title", "Datenpipeline")}
        </Link>
      </p>
    </div>
  );
}
