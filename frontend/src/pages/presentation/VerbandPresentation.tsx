import { Link, useSearchParams } from "react-router-dom";
import { useAppLink } from "../../hooks/useAppLink";
import {
  findVerbandSlide,
  PRESENTATION_SLIDE_QUERY_KEY,
  VERBAND_PRESENTATION_PAGE,
  type VerbandSlide,
} from "../../lib/verbandPresentation";
import { homePaletteColorForTopic } from "../../lib/homePalette";

const accent = homePaletteColorForTopic("verband");

export function VerbandPresentation() {
  const [searchParams] = useSearchParams();
  const link = useAppLink();
  const slide = findVerbandSlide(searchParams.get(PRESENTATION_SLIDE_QUERY_KEY));

  if (!slide) {
    return (
      <div className="mx-auto max-w-[720px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
        <p className="text-label uppercase text-muted mb-2">Präsentation</p>
        <h1 className="text-h1 mb-4">{VERBAND_PRESENTATION_PAGE.missingTitle}</h1>
        <p className="text-body text-muted leading-relaxed mb-6">
          {VERBAND_PRESENTATION_PAGE.missingBody}
        </p>
        <Link
          to={link("/einstieg")}
          className="text-accent hover:text-accent-hover hover:underline"
        >
          Zu den Einstiegen
        </Link>
      </div>
    );
  }

  if (slide.layout === "question") {
    return <QuestionSlide slide={slide} />;
  }

  return <TalkOrArtifactSlide slide={slide} />;
}

function QuestionSlide({ slide }: { slide: VerbandSlide }) {
  return (
    <div className="mx-auto flex min-h-[70vh] max-w-[1080px] flex-col justify-center px-4 pt-10 pb-24 lg:px-8 lg:pt-16">
      <p className="text-label uppercase text-muted mb-6">{slide.eyebrow}</p>
      <p className="text-caption font-medium uppercase tracking-wide text-muted mb-4">
        {slide.title}
      </p>
      <h1 className="text-display max-w-[18ch] text-balance" style={{ color: accent }}>
        {slide.question}
      </h1>
      {slide.lead ? (
        <p className="mt-10 max-w-[48ch] text-body text-muted leading-relaxed">{slide.lead}</p>
      ) : null}
    </div>
  );
}

function TalkOrArtifactSlide({ slide }: { slide: VerbandSlide }) {
  return (
    <div className="mx-auto max-w-[960px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <header className="mb-8 max-w-[72ch]">
        <p className="text-label uppercase text-muted mb-2">{slide.eyebrow}</p>
        <h1 className="text-h1 mb-4" style={{ color: accent }}>
          {slide.title}
        </h1>
        {slide.lead ? (
          <p className="text-body text-foreground leading-relaxed">{slide.lead}</p>
        ) : null}
      </header>

      {slide.paragraphs.length > 0 ? (
        <div className="mb-8 max-w-[72ch] space-y-4">
          {slide.paragraphs.map((p) => (
            <p key={p.slice(0, 48)} className="text-body text-muted leading-relaxed">
              {p}
            </p>
          ))}
        </div>
      ) : null}

      {slide.imageSrc ? (
        <figure className="overflow-hidden rounded-sm border border-border bg-surface">
          <img
            src={slide.imageSrc}
            alt={slide.imageAlt ?? ""}
            className="block h-auto w-full"
            width={1280}
            height={720}
          />
          {slide.imageCaption ? (
            <figcaption className="border-t border-border px-4 py-3 text-small text-muted">
              {slide.imageCaption}
            </figcaption>
          ) : null}
        </figure>
      ) : null}
    </div>
  );
}
