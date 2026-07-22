import { Link, useSearchParams } from "react-router-dom";
import { useLatestEvents, useHomeStats, resolveHomeStats } from "../hooks/useHome";
import { useAppLink } from "../hooks/useAppLink";
import { useMyClub } from "../hooks/useMyClub";
import { buildHomeExampleLinks } from "../lib/homeExamples";import { HOME_FOOTER, HOME_SECTIONS } from "../lib/homeContent";
import { SITE_CONTACT } from "../lib/siteContact";
import { HomeHero } from "../components/home/HomeHero";
import { HomeHeroActions } from "../components/home/HomeHeroActions";
import { HomeExplainerSections } from "../components/home/HomeExplainerSections";
import { HomeEntityMap } from "../components/home/HomeEntityMap";
import { HomeStatsOverview } from "../components/home/HomeStatsOverview";
import { HomeLegacyBridge } from "../components/home/HomeLegacyBridge";
import { HOME_BLOCK_STACK } from "../components/home/HomeSection";

function formatCount(value: number | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("de-DE");
}

export function Home() {
  const statsQuery = useHomeStats();
  const eventsQuery = useLatestEvents(8);
  const stats = resolveHomeStats(statsQuery.data);
  const { active: myClubActive, resolvedClub } = useMyClub();
  const link = useAppLink();

  const games = formatCount(stats?.games);
  const leagueSeasons = formatCount(stats?.league_seasons);
  const years = formatCount(stats?.years);
  const tournaments = formatCount(stats?.tournaments);
  const players = formatCount(stats?.players);

  return (
    <div className="mx-auto max-w-[1080px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <div className={HOME_BLOCK_STACK}>
        <HomeHero myClubActive={myClubActive} resolvedClub={resolvedClub} />

        <HomeStatsOverview
          games={games}
          leagueSeasons={leagueSeasons}
          years={years}
          tournaments={tournaments}
          players={players}
          loading={statsQuery.isPending}
          error={statsQuery.isError}
        />

        <HomeHeroActions myClubActive={myClubActive} resolvedClub={resolvedClub} />

        <HomeEntityMap />
        <HomeExplainerSections />

        <div className="grid gap-8 lg:grid-cols-2">
          <ExampleList />
          <LatestEventsList
            loading={eventsQuery.isPending}
            error={eventsQuery.isError}
            events={eventsQuery.data ?? []}
            database={stats?.database ?? "db_real_merged"}
          />
        </div>

        <HomeLegacyBridge />
      </div>

      <footer className="mt-10 space-y-2 border-t border-border pt-6 text-small text-muted">
        <p>{HOME_FOOTER.dataNote}</p>
        <p>
          Feedback:{" "}
          <a
            href={`mailto:${SITE_CONTACT.email}`}
            className="text-accent hover:text-accent-hover hover:underline"
          >
            {SITE_CONTACT.email}
          </a>
        </p>
        <p>{HOME_FOOTER.cheers}</p>
        <p>
          <Link to={link("/impressum")} className="text-accent hover:text-accent-hover hover:underline">
            Impressum
          </Link>
          {" · "}
          <Link to={link("/glossar")} className="text-accent hover:text-accent-hover hover:underline">
            Glossar
          </Link>
          {" · "}
          <Link
            to={link("/warum-bowlyzer")}
            className="text-accent hover:text-accent-hover hover:underline"
          >
            Warum Bowl-A-Lyzer?
          </Link>
        </p>
      </footer>
    </div>
  );
}

function ExampleList() {
  const [searchParams] = useSearchParams();
  const examples = buildHomeExampleLinks(searchParams);

  return (
    <section className="rounded-sm border border-border bg-surface">
      <header className="border-b border-border px-4 py-3 lg:px-5">
        <h2 className="text-h3">{HOME_SECTIONS.examples}</h2>
      </header>
      <ul className="divide-y divide-border">
        {examples.map((ex) => (
          <li key={ex.label}>
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
  const link = useAppLink();

  return (
    <section
      id={HOME_SECTIONS.latestEventsAnchor}
      className="rounded-sm border border-border bg-surface scroll-mt-8"
    >
      <header className="border-b border-border px-4 py-3 lg:px-5">
        <h2 className="text-h3">{HOME_SECTIONS.latestEvents}</h2>
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
              const href = link("/liga", {
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
