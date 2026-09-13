import { ChevronLeft, ChevronRight, Compass, Undo2, X } from "lucide-react";
import { useEffect } from "react";
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
 * Hidden on ``/einstieg`` (the index).
 * Zurück/Weiter stay available even when off-path so a URL rewrite cannot trap the tour.
 * ArrowLeft / ArrowRight mirror Zurück / Weiter (ignored while typing in fields).
 */
export function StoryChrome() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const parsed = parseStoryQuery(searchParams);
  const active = !!parsed && pathname !== "/einstieg";

  const story = parsed?.story;
  const beatIndex = parsed?.beatIndex ?? 0;
  const beat = story?.beats[beatIndex];
  const onBeatPath =
    !!story && isOnStoryBeatPath(pathname, story, beatIndex, searchParams);
  const isFirst = beatIndex === 0;
  const isLast = !!story && beatIndex === story.beats.length - 1;
  const barStyle = story ? homePaletteBannerStyleForTopic(story.topicKey) : undefined;

  const backHref =
    !story || isFirst
      ? hrefEinstiegIndex(searchParams)
      : hrefForStoryBeat(story, beatIndex - 1, searchParams);
  const nextHref =
    !story || isLast
      ? hrefEinstiegIndex(searchParams)
      : hrefForStoryBeat(story, beatIndex + 1, searchParams);
  const resumeHref = story ? hrefForStoryBeat(story, beatIndex, searchParams) : "/einstieg";

  useEffect(() => {
    if (!active) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      if (isTypingTarget(event.target)) return;

      event.preventDefault();
      void navigate(event.key === "ArrowLeft" ? backHref : nextHref);
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [active, backHref, nextHref, navigate]);

  if (!active || !story || !beat) return null;

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
                : "Du bist abgebogen — zurück zum Schritt oder mit Weiter/Zurück fortfahren."}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-1.5">
            {!onBeatPath ? (
              <Button
                variant="palette"
                size="sm"
                className="border border-current/40 bg-transparent hover:bg-black/10"
                onClick={() => navigate(resumeHref)}
              >
                <Undo2 size={14} strokeWidth={1.75} aria-hidden className="mr-1" />
                Zum Schritt
              </Button>
            ) : null}
            <ButtonLink
              to={backHref}
              variant="palette"
              size="sm"
              className="border border-current/40 bg-transparent hover:bg-black/10"
              title="Zurück (←)"
            >
              <ChevronLeft size={14} strokeWidth={1.75} aria-hidden className="mr-1" />
              {isFirst ? "Einstiege" : "Zurück"}
            </ButtonLink>
            <ButtonLink
              to={nextHref}
              variant="palette"
              size="sm"
              className="bg-surface text-foreground hover:bg-surface-subtle"
              title="Weiter (→)"
            >
              {isLast ? "Einstiege" : "Weiter"}
              {!isLast ? (
                <ChevronRight size={14} strokeWidth={1.75} aria-hidden className="ml-1" />
              ) : null}
            </ButtonLink>
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

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}
