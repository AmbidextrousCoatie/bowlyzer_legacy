import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useEffect } from "react";
import { useAppLink } from "../hooks/useAppLink";
import { EINSTIEG_PAGE, EINSTIEG_STORIES } from "../lib/einstiegStories";
import {
  hrefForStoryBeat,
  stripStoryQuery,
  STORY_BEAT_QUERY_KEY,
  STORY_QUERY_KEY,
} from "../lib/storyQuery";
import { homePaletteColorForTopic, homePaletteStylesForTopic } from "../lib/homePalette";

export function Einstieg() {
  const [searchParams, setSearchParams] = useSearchParams();
  const link = useAppLink();

  useEffect(() => {
    setSearchParams(
      (prev) => {
        if (!prev.get(STORY_QUERY_KEY) && !prev.get(STORY_BEAT_QUERY_KEY)) return prev;
        return stripStoryQuery(prev);
      },
      { replace: true },
    );
  }, [setSearchParams]);

  return (
    <div className="mx-auto max-w-[1080px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <header className="mb-10">
        <p className="text-label uppercase text-muted mb-2">{EINSTIEG_PAGE.eyebrow}</p>
        <h1 className="text-h1 mb-4">{EINSTIEG_PAGE.title}</h1>
        <p className="text-body text-muted max-w-[72ch] leading-relaxed">{EINSTIEG_PAGE.intro}</p>
        <p className="text-body text-muted max-w-[72ch] leading-relaxed mt-2">
          {EINSTIEG_PAGE.hint}
        </p>
      </header>

      <ol className="grid gap-3 sm:grid-cols-2">
        {EINSTIEG_STORIES.map((story, index) => {
          const href = hrefForStoryBeat(story, 0, searchParams);
          const accent = homePaletteColorForTopic(story.topicKey);
          return (
            <li key={story.id}>
              <Link
                to={href}
                style={homePaletteStylesForTopic(story.topicKey)}
                className="group flex h-full flex-col rounded-sm border border-border border-t-[3px] p-4 transition-colors hover:border-border-strong lg:p-5"
              >
                <div className="mb-3 flex items-baseline justify-between gap-3">
                  <span className="font-mono text-caption tabular-nums text-muted">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="text-caption text-muted">
                    {EINSTIEG_PAGE.beatsLabel(story.beats.length)}
                  </span>
                </div>
                <h2 className="text-h3 mb-1" style={{ color: accent }}>
                  {story.persona}
                </h2>
                <p className="text-small text-muted leading-relaxed">{story.job}</p>
                <span className="mt-auto flex items-center gap-1 pt-4 text-small font-medium text-foreground">
                  {EINSTIEG_PAGE.startCta}
                  <ArrowRight
                    size={16}
                    strokeWidth={1.75}
                    className="text-muted group-hover:text-accent"
                    aria-hidden
                  />
                </span>
              </Link>
            </li>
          );
        })}
      </ol>

      <p className="mt-10 text-small text-muted">
        <Link to={link("/")} className="text-accent hover:text-accent-hover hover:underline">
          Zurück zur Übersicht
        </Link>
        {" · "}
        <Link
          to={link("/warum-bowlyzer")}
          className="text-accent hover:text-accent-hover hover:underline"
        >
          Warum Bowl-A-Lyzer?
        </Link>
      </p>
    </div>
  );
}
