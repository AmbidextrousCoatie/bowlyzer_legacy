import { Link, useSearchParams } from "react-router-dom";
import { useMemo } from "react";
import {
  useTournamentCoverage,
  type TournamentCoverageCell,
  type TournamentCoverageStatus,
} from "../../hooks/useTournamentCoverage";
import { useTranslations } from "../../hooks/useTranslations";
import { buildUrl } from "../../lib/api";
import { querySuffixForPath } from "../../lib/navigationQuery";
import { normalizeTournamentGroupName } from "../../lib/tournamentGroupName";const STATUS_LABEL: Record<TournamentCoverageStatus, string> = {
  not_available: "Nicht verfügbar",
  available: "Vorhanden",
  published_flaws: "Veröffentlicht (Mängel)",
  published_ok: "Veröffentlicht (ok)",
};

const STATUS_CLASS: Record<TournamentCoverageStatus, string> = {
  not_available: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
  available: "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200",
  published_flaws: "bg-amber-100 text-amber-950 dark:bg-amber-950 dark:text-amber-100",
  published_ok: "bg-emerald-100 text-emerald-950 dark:bg-emerald-950 dark:text-emerald-100",
};

const STATUS_SYMBOL: Record<TournamentCoverageStatus, string> = {
  not_available: "—",
  available: "○",
  published_flaws: "!",
  published_ok: "✓",
};

function isLinkableStatus(status: TournamentCoverageStatus): boolean {
  return status !== "not_available";
}

function tournamentCellPath(season: string, eventSlug: string): string {
  return buildUrl("/turnier", { season, tournament: eventSlug }, { scope: "tournament" });
}

function cellKey(tournamentId: string, season: string) {
  return `${tournamentId}::${season}`;
}

export function TournamentCoverage() {
  const { t } = useTranslations();
  const [searchParams] = useSearchParams();
  const query = useTournamentCoverage();
  const data = query.data;

  const cellMap = useMemo(() => {
    const map = new Map<string, TournamentCoverageCell>();
    for (const cell of data?.cells ?? []) {
      map.set(cellKey(cell.tournament_id, cell.season), cell);
    }
    return map;
  }, [data?.cells]);

  const pipelineSuffix = querySuffixForPath("/diagnose/datenpipeline", searchParams);

  return (
    <div className="w-full min-w-0 px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <header className="mb-6 lg:mb-8">
        <p className="text-small text-muted mb-2">
          <Link
            to={`/diagnose/datenpipeline${pipelineSuffix}`}
            className="text-primary underline-offset-2 hover:underline"
          >
            {t("ui.diagnosis.pipeline_title", "Datenpipeline")}
          </Link>
          <span className="mx-1.5">/</span>
          <span>{t("ui.diagnosis.tournament_coverage_title", "Turnier-Übersicht")}</span>
        </p>
        <p className="text-label uppercase text-muted mb-2">
          {t("ui.diagnosis.eyebrow", "Diagnose")}
        </p>
        <h1 className="text-h1">
          {t("ui.diagnosis.tournament_coverage_title", "Turnier-Übersicht")}
        </h1>
        <p className="text-body text-muted mt-2 max-w-[72ch]">
          {t(
            "ui.diagnosis.tournament_coverage_desc",
            "Matrix aller bekannten Turniere × Saison: Scraping-Log, GF-Export, Publish und Validierung.",
          )}
        </p>
      </header>

      {query.isLoading && (
        <p className="text-body text-muted">{t("ui.common.loading", "Laden…")}</p>
      )}
      {query.isError && (
        <p className="text-body text-rose-600">
          {t("ui.diagnosis.tournament_coverage_error", "Turnier-Übersicht konnte nicht geladen werden.")}
        </p>
      )}

      {data && (
        <>
          <section className="mt-6 flex flex-wrap gap-3">
            {(Object.keys(STATUS_LABEL) as TournamentCoverageStatus[]).map((status) => (
              <div
                key={status}
                className={`rounded-sm border border-border px-3 py-2 text-caption ${STATUS_CLASS[status]}`}
              >
                <span className="font-mono mr-1.5">{STATUS_SYMBOL[status]}</span>
                {STATUS_LABEL[status]}: {data.summary[status] ?? 0}
              </div>
            ))}
          </section>

          <p className="mt-4 text-caption text-muted">
            {t("ui.diagnosis.tournament_coverage_sources", "Quellen")}:{" "}
            {data.sources.scrape_log_present ? "Scrape-Log" : "kein Scrape-Log"}
            {" · "}
            {data.sources.gf_input_present ? "GF" : "kein GF"}
            {" · "}
            {data.sources.published_present ? "Published" : "nicht published"}
            {" · "}
            {data.sources.quality_report_present ? "Validierung" : "keine Validierung"}
            {" · "}
            {data.sources.published_pairs} published / {data.sources.download_pairs} Downloads
          </p>

          <section className="mt-8 rounded-sm border border-border bg-surface overflow-x-auto w-full">
            <table className="w-full text-caption text-left border-collapse">
              <thead>
                <tr className="border-b border-border text-label uppercase text-muted">
                  <th className="sticky left-0 z-10 bg-surface px-3 py-2 font-medium min-w-[12rem]">
                    {t("ui.tournament.tournament", "Turnier")}
                  </th>
                  {data.seasons.map((season) => (
                    <th
                      key={season}
                      className="px-2 py-2 font-medium text-center whitespace-nowrap min-w-[3.25rem]"
                    >
                      {season}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.tournaments.map((tournament) => (
                  <tr key={tournament.id} className="border-t border-border">
                    <th
                      scope="row"
                      className="sticky left-0 z-10 bg-surface px-3 py-2 text-left font-medium text-body whitespace-nowrap"
                      title={tournament.long_name}
                    >
                      <span className="font-mono text-small text-muted mr-2">{tournament.id}</span>
                      {tournament.long_name}
                    </th>
                    {data.seasons.map((season) => {
                      const cell = cellMap.get(cellKey(tournament.id, season));
                      const status = cell?.status ?? "not_available";
                      const title = [
                        STATUS_LABEL[status],
                        cell?.row_count ? `${cell.row_count} Zeilen` : "",
                        cell?.sources?.length ? `Quellen: ${cell.sources.join(", ")}` : "",
                        cell?.notes || "",
                      ]
                        .filter(Boolean)
                        .join(" · ");
                      const eventSlug =
                        cell?.event_slug ||
                        normalizeTournamentGroupName(tournament.long_name);
                      const symbol = STATUS_SYMBOL[status];
                      const canLink = isLinkableStatus(status) && Boolean(eventSlug);
                      return (
                        <td key={season} className="px-1 py-1 text-center align-middle">
                          {canLink ? (
                            <Link
                              to={tournamentCellPath(season, eventSlug)}
                              title={title}
                              className={`inline-flex h-7 min-w-[1.75rem] items-center justify-center rounded-sm px-1 font-mono text-small text-accent hover:text-accent-hover hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring ${STATUS_CLASS[status]}`}
                            >
                              {symbol}
                            </Link>
                          ) : (
                            <span
                              title={title}
                              className={`inline-flex h-7 min-w-[1.75rem] items-center justify-center rounded-sm px-1 font-mono text-small ${STATUS_CLASS[status]}`}
                            >
                              {symbol}
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="mt-6 text-caption text-muted max-w-[72ch]">
            <p>
              {t(
                "ui.diagnosis.tournament_coverage_legend",
                "— nicht auffindbar · ○ heruntergeladen/importiert, nicht published · ! published mit Validierungsmängeln · ✓ published ohne Mängel. Klick auf ○/!/✓ öffnet das Turnier.",
              )}
            </p>
          </section>
        </>
      )}
    </div>
  );
}
