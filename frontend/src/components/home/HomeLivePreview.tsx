import { Link } from "react-router-dom";
import { useAvailableSeasons, useSeasonLeagueStandings } from "../../hooks/useLeague";
import { useAppLink } from "../../hooks/useAppLink";
import { buildUrl } from "../../lib/api";
import { HOME_SECTIONS } from "../../lib/homeContent";
import {
  buildStandingsPreview,
  preferLeagueEntry,
} from "../../lib/homeStandingsPreview";
import { pickLatestSeason } from "../../lib/leagueSeason";

export function HomeLivePreview() {
  const link = useAppLink();
  const seasonsQuery = useAvailableSeasons();
  const latestSeason = pickLatestSeason(seasonsQuery.data ?? []);
  const standingsQuery = useSeasonLeagueStandings(latestSeason);

  const leagueEntry = preferLeagueEntry(standingsQuery.data?.leagues ?? []);
  const preview =
    leagueEntry != null
      ? buildStandingsPreview(leagueEntry.standings, {
          league: leagueEntry.league,
          leagueLong: leagueEntry.league_long,
          week: leagueEntry.week,
        })
      : null;

  const loading = seasonsQuery.isPending || standingsQuery.isPending;
  const error = seasonsQuery.isError || standingsQuery.isError;

  const title = preview?.leagueLong || preview?.league || "Bayernliga";
  const href =
    latestSeason && preview
      ? buildUrl("/liga", {
          season: latestSeason,
          league: preview.league,
        })
      : buildUrl("/liga", { season: "latest" });

  return (
    <section className="py-10" aria-labelledby="home-preview-title">
      <p className="text-label uppercase text-muted mb-2">{HOME_SECTIONS.preview}</p>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="home-preview-title" className="text-h2">
            {title}
            {preview ? (
              <span className="text-muted font-normal">
                {" "}
                · Spieltag <span className="font-mono">{preview.week}</span>
              </span>
            ) : null}
          </h2>
          <p className="mt-1 text-small text-muted">{HOME_SECTIONS.previewHint}</p>
        </div>
        <Link
          to={link(href)}
          className="inline-flex min-h-[44px] items-center text-small font-medium text-accent hover:text-accent-hover hover:underline"
        >
          Vollständige Tabelle
        </Link>
      </div>

      {loading ? <PreviewSkeleton /> : null}
      {error ? (
        <p className="text-small text-danger-fg">Vorschau konnte nicht geladen werden.</p>
      ) : null}
      {!loading && !error && preview ? <PreviewTable preview={preview} /> : null}
      {!loading && !error && !preview ? (
        <p className="text-small text-muted">Keine Tabellendaten für die Vorschau verfügbar.</p>
      ) : null}
    </section>
  );
}

function PreviewTable({
  preview,
}: {
  preview: NonNullable<ReturnType<typeof buildStandingsPreview>>;
}) {
  return (
    <div className="overflow-x-auto rounded-sm border border-border bg-surface">
      <table className="w-full min-w-[320px] border-collapse text-small">
        <thead>
          <tr className="border-b border-border bg-surface-subtle">
            {preview.headers.map((header) => (
              <th
                key={header}
                className="px-4 py-2.5 text-left text-label uppercase text-muted font-medium"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {preview.rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-b border-border last:border-b-0">
              {row.cells.map((cell, cellIndex) => (
                <td
                  key={cellIndex}
                  className={
                    "px-4 py-2.5 " +
                    (cellIndex === 0 ? "font-mono tabular-nums text-muted" : "text-foreground")
                  }
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PreviewSkeleton() {
  return (
    <div className="overflow-hidden rounded-sm border border-border bg-surface">
      <div className="h-10 animate-pulse bg-surface-subtle" />
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-9 animate-pulse border-t border-border bg-surface" />
      ))}
    </div>
  );
}
