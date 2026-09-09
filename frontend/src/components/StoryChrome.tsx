import { ChevronLeft, ChevronRight, Compass, Undo2, X } from "lucide-react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Button, ButtonLink } from "./Button";
import {
  hrefEinstiegIndex,
  hrefForStoryBeat,
  isOnStoryBeatPath,
  parseStoryQuery,
  STORY_BEAT_QUERY_KEY,
  STORY_QUERY_KEY,
} from "../lib/storyQuery";
import { homePaletteBannerStyleForTopic } from "../lib/homePalette";

/**
 * Sticky rundgang bar while ``?story=`` & ``?beat=`` are set.
 * Hidden on ``/einstieg`` (the index). Off-path shows a resume/exit pair.
 */
export function StoryChrome() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const parsed = parseStoryQuery(searchParams);

  if (!parsed || pathname === "/einstieg") return null;

  const { story, beatIndex } = parsed;
  const beat = story.beats[beatIndex];
  const onBeatPath = isOnStoryBeatPath(pathname, story, beatIndex);
  const isFirst = beatIndex === 0;
  const isLast = beatIndex === story.beats.length - 1;
  const barStyle = homePaletteBannerStyleForTopic(story.topicKey);

  const backHref = isFirst
    ? hrefEinstiegIndex(searchParams)
    : hrefForStoryBeat(story, beatIndex - 1, searchParams);
  const nextHref = isLast
    ? hrefEinstiegIndex(searchParams)
    : hrefForStoryBeat(story, beatIndex + 1, searchParams);
  const resumeHref = hrefForStoryBeat(story, beatIndex, searchParams);

  function endStory() {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete(STORY_QUERY_KEY);
        next.delete(STORY_BEAT_QUERY_KEY);
        return next;
      },
      { replace: true },
    );
  }

  return (
    <div role="region" aria-label="Einstieg" style={barStyle}>
      <div className="mx-auto flex max-w-[1280px] items-stretch px-4 lg:px-8">
        <div className="flex min-w-0 flex-1 flex-col gap-2 py-2.5 sm:flex-row sm:items-center sm:gap-3">
          <span className="grid size-8 shrink-0 place-items-center rounded-sm bg-black/10">
            <Compass size={16} strokeWidth={1.75} aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-label uppercase tracking-wide opacity-90">
              Einstieg · {beatIndex + 1}/{story.beats.length}
            </p>
            <p className="truncate text-body font-semibold">{story.persona}</p>
            <p className="text-small leading-relaxed opacity-85">
              {onBeatPath
                ? beat.caption
                : "Du bist abgebogen — zurück zum Schritt oder Rundgang beenden."}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-1.5">
            {onBeatPath ? (
              <>
                <ButtonLink
                  to={backHref}
                  variant="palette"
                  size="sm"
                  className="border border-current/40 bg-transparent hover:bg-black/10"
                >
                  <ChevronLeft size={14} strokeWidth={1.75} aria-hidden className="mr-1" />
                  {isFirst ? "Einstiege" : "Zurück"}
                </ButtonLink>
                <ButtonLink
                  to={nextHref}
                  variant="palette"
                  size="sm"
                  className="bg-surface text-foreground hover:bg-surface-subtle"
                >
                  {isLast ? "Einstiege" : "Weiter"}
                  {!isLast ? (
                    <ChevronRight size={14} strokeWidth={1.75} aria-hidden className="ml-1" />
                  ) : null}
                </ButtonLink>
              </>
            ) : (
              <Button
                variant="palette"
                size="sm"
                className="bg-surface text-foreground hover:bg-surface-subtle"
                onClick={() => navigate(resumeHref)}
              >
                <Undo2 size={14} strokeWidth={1.75} aria-hidden className="mr-1" />
                Zum Schritt
              </Button>
            )}
            <button
              type="button"
              onClick={endStory}
              aria-label="Rundgang beenden"
              title="Rundgang beenden"
              className="grid size-8 place-items-center rounded-sm hover:bg-black/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              <X size={16} strokeWidth={1.75} aria-hidden />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
