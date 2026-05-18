import { Link } from "react-router-dom";
import { SITE_CONTACT } from "../lib/siteContact";

export function Impressum() {
  return (
    <div className="mx-auto max-w-[720px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <p className="text-label uppercase text-muted mb-2">Rechtliches</p>
      <h1 className="text-h1 mb-8">Impressum</h1>

      <article className="space-y-8 text-body text-foreground">
        <section>
          <h2 className="text-h2 mb-3">Angaben gemäß § 5 TMG</h2>
          <p className="text-muted leading-relaxed">
            Verantwortlich für den Inhalt nach § 55 Abs. 2 RStV:
          </p>
          <p className="mt-2 leading-relaxed">
            {SITE_CONTACT.name}
            <br />
            {SITE_CONTACT.street}
            <br />
            {SITE_CONTACT.city}
            <br />
            E-Mail:{" "}
            <a
              href={`mailto:${SITE_CONTACT.email}`}
              className="text-accent hover:text-accent-hover hover:underline"
            >
              {SITE_CONTACT.email}
            </a>
          </p>
        </section>

        <section>
          <h2 className="text-h2 mb-3">Haftung für Inhalte</h2>
          <p className="leading-relaxed text-muted">
            Die Inhalte dieser Seiten wurden mit größter Sorgfalt erstellt. Für die Richtigkeit,
            Vollständigkeit und Aktualität der Inhalte können wir jedoch keine Gewähr übernehmen.
            Als Diensteanbieter sind wir gemäß § 7 Abs. 1 TMG für eigene Inhalte auf diesen Seiten
            nach den allgemeinen Gesetzen verantwortlich.
          </p>
        </section>

        <section>
          <h2 className="text-h2 mb-3">Haftung für Links</h2>
          <p className="leading-relaxed text-muted">
            Unser Angebot enthält Links zu externen Websites Dritter, auf deren Inhalte wir keinen
            Einfluss haben. Für die Inhalte der verlinkten Seiten ist stets der jeweilige Anbieter
            oder Betreiber verantwortlich.
          </p>
        </section>

        <section>
          <h2 className="text-h2 mb-3">Urheberrecht</h2>
          <p className="leading-relaxed text-muted">
            Die durch die Seitenbetreiber erstellten Inhalte und Werke auf diesen Seiten unterliegen
            dem deutschen Urheberrecht. Die Vervielfältigung, Bearbeitung, Verbreitung und jede Art
            der Verwertung außerhalb der Grenzen des Urheberrechtes bedürfen der schriftlichen
            Zustimmung des jeweiligen Autors bzw. Erstellers.
          </p>
        </section>

        <section>
          <h2 className="text-h2 mb-3">Datenschutz</h2>
          <p className="leading-relaxed text-muted">
            Die Nutzung unserer Webseite ist in der Regel ohne Angabe personenbezogener Daten
            möglich. Soweit auf unseren Seiten personenbezogene Daten erhoben werden, erfolgt dies,
            soweit möglich, stets auf freiwilliger Basis. Diese Daten werden ohne Ihre ausdrückliche
            Zustimmung nicht an Dritte weitergegeben.
          </p>
        </section>

        <section className="rounded-sm border border-border bg-surface-subtle p-4">
          <h2 className="text-h3 mb-2">Technische Informationen</h2>
          <dl className="grid gap-2 text-small">
            <div className="flex flex-wrap gap-x-2">
              <dt className="font-medium text-foreground">Anwendung</dt>
              <dd className="text-muted">Bowl-A-Lyzer</dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="font-medium text-foreground">Beschreibung</dt>
              <dd className="text-muted">Webanwendung zur Analyse von Bowling-Liga-Daten</dd>
            </div>
          </dl>
        </section>

        <p className="text-small text-muted border-t border-border pt-6">
          <Link to="/" className="text-accent hover:text-accent-hover hover:underline">
            Zur Startseite
          </Link>
        </p>
      </article>
    </div>
  );
}
