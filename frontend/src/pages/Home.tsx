import { Link } from "react-router-dom";
import { useLatestEvents, useHomeStats, resolveHomeStats } from "../hooks/useHome";
import { HOME_EXAMPLE_LINKS } from "../lib/homeExamples";
import { buildUrl } from "../lib/api";
import { SITE_CONTACT } from "../lib/siteContact";

function formatCount(value: number | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("de-DE");
}

export function Home() {
  const statsQuery = useHomeStats();
  const eventsQuery = useLatestEvents(8);
  const stats = resolveHomeStats(statsQuery.data);

  return (
    <div className="mx-auto max-w-[1080px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <header className="mb-10">
        <p className="text-label uppercase text-muted mb-2">Bowl-A-Lyzer</p>
        <h1 className="text-h1 mb-4">Willkommen</h1>
        <p className="text-body text-muted max-w-[72ch] leading-relaxed">
          Diese Seite ist ein Proof of Concept zur Darstellung von Ergebnissen und Statistiken rund
          um Bowling-Ligen, Turniere und Pokalwettbewerbe. Ich verwende die offiziellen Daten der <a href="https://bowlingbayern.de/BBU" target="_blank" rel="noopener noreferrer">Bayerischen Bowling Union</a> und bin stetig dabei, die Datenbasis zu erweitern. 
          Die Auswertungen findest du in der Navigation — oder starte mit einem der Beispiele unten.
        </p>
        <p className="mt-4 text-body text-muted max-w-[72ch] leading-relaxed">
          Feedback und Vorschläge gerne per E-Mail an{" "}
          <a
            href={`mailto:${SITE_CONTACT.email}`}
            className="text-accent hover:text-accent-hover hover:underline"
          >
            {SITE_CONTACT.email}
          </a>
          .
        </p>
        <p className="mt-3 text-small text-muted">Cheers, Chris</p>
      </header>

      <section className="mb-10" aria-label="Überblick">
        <h2 className="text-h2 mb-4">Daten im Überblick</h2>
        {statsQuery.isError && (
          <p className="text-small text-danger-fg mb-4">
            Statistiken konnten nicht geladen werden.
          </p>
        )}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <StatCard label="Spiele" value={formatCount(stats?.games)} loading={statsQuery.isPending} />
          <StatCard
            label="Liga-Saisons"
            value={formatCount(stats?.league_seasons)}
            loading={statsQuery.isPending}
          />
          <StatCard
            label="Jahre"
            value={formatCount(stats?.years)}
            loading={statsQuery.isPending}
          />
          <StatCard
            label="Turniere"
            value={formatCount(stats?.tournaments)}
            loading={statsQuery.isPending}
          />
          <StatCard
            label="Spieler"
            value={formatCount(stats?.players)}
            loading={statsQuery.isPending}
          />
        </div>
      </section>

      <div className="grid gap-8 lg:grid-cols-2">
        <ExampleList />
        <LatestEventsList
          loading={eventsQuery.isPending}
          error={eventsQuery.isError}
          events={eventsQuery.data ?? []}
          database={stats?.database ?? "db_real_merged"}
        />
      </div>

      <p className="mt-8 text-small text-muted">
        <Link to="/impressum" className="text-accent hover:text-accent-hover hover:underline">
          Impressum
        </Link>
      </p>
    </div>
  );
}

function ExampleList() {
  return (
    <section className="rounded-sm border border-border bg-surface">
      <header className="border-b border-border px-4 py-3 lg:px-5">
        <h2 className="text-h3">Beispiele</h2>
      </header>
      <ul className="divide-y divide-border">
        {HOME_EXAMPLE_LINKS.map((ex) => (
          <li key={ex.to}>
            <Link
              to={ex.to}
              className="block px-4 py-3 text-small text-accent hover:bg-surface-subtle hover:text-accent-hover lg:px-5"
            >
              {ex.label}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function LatestEventsList({
  loading,
  error,
  events,
  database,
}: {
  loading: boolean;
  error: boolean;
  events: Array<{ Season: string; League: string; Week: number | string; Date: string }>;
  database: string;
}) {
  return (
    <section className="rounded-sm border border-border bg-surface">
      <header className="border-b border-border px-4 py-3 lg:px-5">
        <h2 className="text-h3">Letzte Events</h2>
      </header>
      {loading && <p className="px-4 py-4 text-small text-muted lg:px-5">Laden…</p>}
      {error && (
        <p className="px-4 py-4 text-small text-danger-fg lg:px-5">
          Events konnten nicht geladen werden.
        </p>
      )}
      {!loading && !error && (
        <ul className="divide-y divide-border">
          {events.length === 0 ? (
            <li className="px-4 py-4 text-small text-muted lg:px-5">Keine Events gefunden.</li>
          ) : (
            events.map((ev) => {
              const href = buildUrl("/liga", {
                season: ev.Season,
                league: ev.League,
                week: String(ev.Week),
                database,
              });
              return (
                <li key={`${ev.Season}-${ev.League}-${ev.Week}-${ev.Date}`}>
                  <Link
                    to={href}
                    className="block px-4 py-3 text-small hover:bg-surface-subtle lg:px-5"
                  >
                    <span className="font-medium text-foreground">
                      {ev.Season} · {ev.League} · Spieltag {ev.Week}
                    </span>
                    {ev.Date ? (
                      <span className="mt-0.5 block text-muted">({ev.Date})</span>
                    ) : null}
                  </Link>
                </li>
              );
            })
          )}
        </ul>
      )}
    </section>
  );
}

function StatCard({
  label,
  value,
  loading,
}: {
  label: string;
  value: string;
  loading?: boolean;
}) {
  return (
    <div className="rounded-sm border border-border bg-surface px-4 py-3">
      <p className="text-label uppercase text-muted mb-1">{label}</p>
      <p className="font-mono text-h2 tabular-nums text-foreground">
        {loading ? (
          <span className="inline-block h-7 w-16 animate-pulse rounded-xs bg-surface-subtle" />
        ) : (
          value
        )}
      </p>
    </div>
  );
}
