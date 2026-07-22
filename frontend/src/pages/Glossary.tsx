import { Link } from "react-router-dom";
import { GLOSSARY_ENTRIES } from "../lib/homeContent";
import { TopicPageHeader } from "../components/TopicPageHeader";

export function Glossary() {
  return (
    <div className="mx-auto max-w-[720px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <TopicPageHeader
        topic="glossary"
        eyebrow="Bowl-A-Lyzer"
        className="mb-10"
        title="Glossar"
        description="Kurze Erklärungen zu Begriffen in Liga- und Turnierergebnissen."
      />

      <dl className="divide-y divide-border rounded-sm border border-border bg-surface">
        {GLOSSARY_ENTRIES.map((entry) => (
          <div key={entry.term} className="px-5 py-4">
            <dt className="text-h3 mb-1">{entry.term}</dt>
            <dd className="text-body text-muted leading-relaxed">{entry.definition}</dd>
          </div>
        ))}
      </dl>

      <p className="mt-8 text-small text-muted">
        <Link to="/" className="text-accent hover:text-accent-hover hover:underline">
          Zurück zur Übersicht
        </Link>
      </p>
    </div>
  );
}
