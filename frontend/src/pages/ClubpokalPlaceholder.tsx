import { Link } from "react-router-dom";
import { CLUBPOKAL_PLACEHOLDER } from "../lib/homeContent";
import { TopicPageHeader } from "../components/TopicPageHeader";

export function ClubpokalPlaceholder() {
  return (
    <div className="mx-auto max-w-[720px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <TopicPageHeader
        topic="clubpokal"
        eyebrow="Bowl-A-Lyzer"
        className="mb-6"
        title={CLUBPOKAL_PLACEHOLDER.title}
        description={CLUBPOKAL_PLACEHOLDER.headline}
      />

      <p className="text-body text-muted leading-relaxed max-w-[72ch]">{CLUBPOKAL_PLACEHOLDER.body}</p>

      <p className="mt-8 text-small text-muted">
        <Link to="/" className="text-accent hover:text-accent-hover hover:underline">
          Zurück zur Übersicht
        </Link>
      </p>
    </div>
  );
}
