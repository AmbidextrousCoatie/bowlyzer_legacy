import type {
  TournamentBestEfforts,
  TournamentBestEffortsSection,
  TournamentEffortEntry,
} from "../../../hooks/useTournament";

type Props = {
  bestEfforts: TournamentBestEfforts | undefined | null;
  t: (key: string, fallback?: string) => string;
};

export function BestEfforts({ bestEfforts, t }: Props) {
  const sections = bestEfforts?.sections ?? [];
  const n = bestEfforts?.n ?? 5;

  if (sections.length === 0) return null;

  return (
    <section>
      <div className="mb-4">
        <p className="text-label uppercase text-muted mb-1.5">
          {t("ui.tournament.best_efforts_eyebrow", "Bestleistungen")}
        </p>
        <h2 className="text-h2">
          {t("ui.tournament.best_efforts_top_n", "Bestleistungen (Top {n})").replace(
            "{n}",
            String(n),
          )}
        </h2>
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        {sections.map((section, idx) => (
          <ScopeBlock key={section.scope ?? idx} section={section} t={t} />
        ))}
      </div>
    </section>
  );
}

function ScopeBlock({
  section,
  t,
}: {
  section: TournamentBestEffortsSection;
  t: (key: string, fallback?: string) => string;
}) {
  return (
    <div className="rounded-sm border border-border bg-surface p-4">
      <p className="text-label uppercase text-subtle mb-3">{section.scope ?? ""}</p>
      <div className="space-y-4">
        <EffortGroup
          title={t("ui.tournament.best_games", "Beste Spiele")}
          items={section.best_games ?? []}
          t={t}
        />
        <EffortGroup
          title={t("ui.tournament.best_pairs", "Beste Paare")}
          items={section.best_pairs ?? []}
          t={t}
        />
        <EffortGroup
          title={t("ui.tournament.best_blocks", "Beste Blöcke")}
          items={section.best_blocks ?? []}
          t={t}
        />
      </div>
    </div>
  );
}

function EffortGroup({
  title,
  items,
  t,
}: {
  title: string;
  items: TournamentEffortEntry[];
  t: (key: string, fallback?: string) => string;
}) {
  return (
    <div>
      <p className="text-caption text-muted mb-1.5">{title}</p>
      {items.length === 0 ? (
        <p className="text-small text-muted italic">
          {t("ui.tournament.no_entries", "Keine Einträge")}
        </p>
      ) : (
        <ul className="space-y-1">
          {items.map((entry, idx) => (
            <li
              key={`${entry.player ?? "unknown"}-${idx}`}
              className="flex items-baseline justify-between border-b border-border pb-1.5 last:border-b-0"
            >
              <span className="text-small text-foreground">
                {entry.player ?? t("ui.tournament.unknown", "Unbekannt")}
                {entry.club ? (
                  <span className="text-muted"> ({compactClub(entry.club)})</span>
                ) : null}
              </span>
              <span className="text-small font-mono font-semibold text-foreground tabular-nums">
                {entry.display_value ?? entry.value ?? ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function compactClub(club: string): string {
  const sep = " - ";
  const idx = club.indexOf(sep);
  if (idx >= 0 && idx + sep.length < club.length) {
    return club.slice(idx + sep.length).trim();
  }
  return club;
}
