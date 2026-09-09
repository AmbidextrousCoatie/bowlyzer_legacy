import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { useHomeStats, resolveHomeStats } from "../hooks/useHome";
import { useAppLink } from "../hooks/useAppLink";
import { HOME_HISTORY, WHY_BOWLYZER } from "../lib/homeContent";
import { SITE_CONTACT } from "../lib/siteContact";

function formatCount(value: number | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("de-DE");
}

export function WhyBowlyzer() {
  const statsQuery = useHomeStats();
  const stats = resolveHomeStats(statsQuery.data);
  const link = useAppLink();

  const games = formatCount(stats?.games);
  const leagueSeasons = formatCount(stats?.league_seasons);
  const years = formatCount(stats?.years);
  const tournaments = formatCount(stats?.tournaments);
  const players = formatCount(stats?.players);

  return (
    <div className="mx-auto max-w-[720px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <header className="mb-10">
        <p className="text-label uppercase text-muted mb-2">{WHY_BOWLYZER.eyebrow}</p>
        <h1 className="text-h1 mb-4">{WHY_BOWLYZER.title}</h1>
        <p className="text-body text-muted leading-relaxed">{WHY_BOWLYZER.intro}</p>
        <p className="mt-4 text-body">
          <Link
            to={link("/einstieg")}
            className="text-accent hover:text-accent-hover hover:underline"
          >
            {WHY_BOWLYZER.einstiegCta}
          </Link>
        </p>
      </header>

      <div className="space-y-10">
        <ContentSection title={WHY_BOWLYZER.motivation.title}>
          {WHY_BOWLYZER.motivation.paragraphs.map((p) => (
            <p key={p.slice(0, 40)} className="text-body text-muted leading-relaxed">
              {p}
            </p>
          ))}
        </ContentSection>

        <section
          className="rounded-sm bg-accent-tint px-5 py-8 lg:px-8"
          aria-labelledby="why-history-title"
        >
          <p className="text-label uppercase text-muted mb-2">{HOME_HISTORY.eyebrow}</p>
          <h2 id="why-history-title" className="text-h2 mb-6">
            {HOME_HISTORY.title}
          </h2>
          <ol className="space-y-4">
            {HOME_HISTORY.timeline.map((item) => (
              <li key={item.era} className="flex gap-4">
                <span className="w-16 shrink-0 text-label uppercase text-accent">{item.era}</span>
                <p className="text-body text-muted leading-relaxed">{item.text}</p>
              </li>
            ))}
          </ol>
          {!statsQuery.isError ? (
            <p className="mt-6 font-mono text-small tabular-nums text-foreground">
              {HOME_HISTORY.statsIntro(games, leagueSeasons, years, tournaments, players)}
            </p>
          ) : null}
        </section>

        <ContentSection title={WHY_BOWLYZER.dataSources.title}>
          {WHY_BOWLYZER.dataSources.paragraphs.map((p) => (
            <p key={p.slice(0, 40)} className="text-body text-muted leading-relaxed">
              {p}
            </p>
          ))}
          <p className="text-body text-muted">
            <a
              href={WHY_BOWLYZER.dataSources.bbuUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:text-accent-hover hover:underline"
            >
              {WHY_BOWLYZER.dataSources.bbuLabel}
            </a>
          </p>
        </ContentSection>

        <ContentSection title={WHY_BOWLYZER.leagueFormats.title}>
          {WHY_BOWLYZER.leagueFormats.paragraphs.map((p) => (
            <p key={p.slice(0, 40)} className="text-body text-muted leading-relaxed">
              {p}
            </p>
          ))}
          <ul className="list-disc space-y-2 pl-5 text-body text-muted">
            {WHY_BOWLYZER.leagueFormats.bullets.map((bullet) => (
              <li key={bullet}>{bullet}</li>
            ))}
          </ul>
        </ContentSection>

        <ContentSection title={WHY_BOWLYZER.behindTheScenes.title}>
          {WHY_BOWLYZER.behindTheScenes.paragraphs.map((p) => (
            <p key={p.slice(0, 40)} className="text-body text-muted leading-relaxed">
              {p}
            </p>
          ))}
          <p className="text-body text-muted">
            Feedback:{" "}
            <a
              href={`mailto:${SITE_CONTACT.email}`}
              className="text-accent hover:text-accent-hover hover:underline"
            >
              {SITE_CONTACT.email}
            </a>
          </p>
        </ContentSection>
      </div>

      <p className="mt-10 text-small text-muted">
        <Link to={link("/")} className="text-accent hover:text-accent-hover hover:underline">
          Zurück zur Übersicht
        </Link>
        {" · "}
        <Link
          to={link("/einstieg")}
          className="text-accent hover:text-accent-hover hover:underline"
        >
          Einstieg
        </Link>
      </p>
    </div>
  );
}

function ContentSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-h2">{title}</h2>
      <div className="space-y-3">{children}</div>
    </section>
  );
}
