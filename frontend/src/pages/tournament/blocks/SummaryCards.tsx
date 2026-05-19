import type { TournamentSummaryCard } from "../../../hooks/useTournament";

type Props = {
  cards: TournamentSummaryCard[];
  /** Active stage name or overall label (not the tournament's latest round). */
  overviewStageLabel: string;
  onPlayerClick: (player: string) => void;
  t: (key: string, fallback?: string) => string;
};

export function SummaryCards({ cards, overviewStageLabel, onPlayerClick, t }: Props) {
  if (!cards || cards.length === 0) {
    return null;
  }

  const tournamentCard = cards.find((c) => normalizeTitle(c.title) === "tournament");
  const innerCards = cards.filter(
    (c) =>
      c !== tournamentCard && normalizeTitle(c.title) !== "current round",
  );

  const titlePrimary = tournamentCard?.value ?? t("ui.tournament.tournament", "Turnier");
  const titleSubtitle = tournamentCard?.subtitle ?? "";

  return (
    <section>
      <div className="mb-4">
        <p className="text-label uppercase text-muted mb-1.5">
          {t("ui.tournament.overview", "Turnierübersicht")}
        </p>
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="text-h2">
            {String(titlePrimary)}
            {titleSubtitle ? (
              <span className="text-muted font-normal"> — {String(titleSubtitle)}</span>
            ) : null}
          </h2>
          <p className="text-small font-semibold text-foreground">{overviewStageLabel}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {innerCards.map((card, idx) => (
          <SummaryCard
            key={`${card.title ?? "card"}-${idx}`}
            card={card}
            onPlayerClick={onPlayerClick}
            t={t}
          />
        ))}
      </div>
    </section>
  );
}

function SummaryCard({
  card,
  onPlayerClick,
  t,
}: {
  card: TournamentSummaryCard;
  onPlayerClick: (player: string) => void;
  t: (key: string, fallback?: string) => string;
}) {
  const title = localizeCardTitle(card.title ?? "", t);
  const subtitle = localizeCardSubtitle(card.subtitle ?? "", t);
  const value = card.value ?? "";

  const isPlayer = isPlayerCard(card);
  const isWinner = !isPlayerCard(card)
    ? false
    : (() => {
        const t = String(card.title || "").toLowerCase();
        return t.includes("leader") || t.includes("winner");
      })();

  return (
    <div
      className={
        "rounded-sm border p-4 " +
        (isWinner ? "border-accent bg-accent-tint" : "border-border bg-surface")
      }
    >
      <p className="text-label uppercase text-muted mb-2">{title}</p>
      <p className="text-stat-md font-semibold text-foreground">
        {isPlayer && value ? (
          <button
            type="button"
            className="text-accent hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            onClick={() => onPlayerClick(String(value))}
          >
            {String(value)}
          </button>
        ) : (
          String(value)
        )}
      </p>
      {subtitle ? <p className="text-caption text-muted mt-1">{subtitle}</p> : null}
    </div>
  );
}

function normalizeTitle(title?: string | null): string {
  return String(title ?? "")
    .trim()
    .toLowerCase();
}

function isPlayerCard(card: TournamentSummaryCard): boolean {
  const title = String(card.title ?? "").toLowerCase();
  const value = String(card.value ?? "").trim();
  if (!value) return false;
  if (["n/a", "-", "unknown"].includes(value.toLowerCase())) return false;
  return title.includes("leader") || title.includes("winner") || title.includes("cut line");
}

function localizeCardTitle(raw: string, t: (key: string, fallback?: string) => string): string {
  const key = raw.trim();
  switch (key) {
    case "Tournament":
      return t("ui.tournament.card.tournament", "Turnier");
    case "Current Round":
      return t("ui.tournament.card.current_round", "Aktuelle Runde");
    case "Cut Line":
      return t("ui.tournament.card.cut_line", "Cut-Line");
    case "Tournament Leader":
      return t("ui.tournament.card.tournament_leader", "Turnierführung");
    case "Participants":
      return t("ui.tournament.card.participants", "Teilnehmende");
    case "Stage Winner":
      return t("ui.tournament.card.stage_winner", "Sieger der Runde");
    default:
      return key;
  }
}

function localizeCardSubtitle(raw: string, t: (key: string, fallback?: string) => string): string {
  if (raw.trim() === "Field size") return t("ui.tournament.card.field_size", "Teilnehmerzahl");
  return raw;
}
