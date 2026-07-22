import { Link } from "react-router-dom";
import { resolveSpecialMatchNavPath } from "../../../lib/leagueNavigation";
import type { SpecialMatchRow, SpecialMatches } from "../../../hooks/useTeam";

type Props = {
  teamName: string;
  data: SpecialMatches;
  t: (key: string, fallback?: string) => string;
};

type BlockSpec = {
  key: string;
  title: string;
  rows: SpecialMatchRow[];
  showMargin: boolean;
};

function formatEvent(match: SpecialMatchRow): string {
  const round =
    match.Round != null && String(match.Round) !== "0" ? ` S${match.Round}` : "";
  return `${match.Season ?? ""} ${match.League ?? ""} W${match.Week ?? ""}${round}`.trim();
}

function formatMargin(margin: number | undefined | null): string {
  if (margin == null || Number.isNaN(margin)) return "—";
  if (margin > 0) return `+${margin}`;
  return String(margin);
}

export function SpecialMatchesSection({ teamName, data, t }: Props) {
  const blocks: BlockSpec[] = [
    {
      key: "high",
      title: t("ui.special.highest_scores", "Höchste Ergebnisse"),
      rows: data.highest_scores ?? [],
      showMargin: false,
    },
    {
      key: "low",
      title: t("ui.special.lowest_scores", "Niedrigste Ergebnisse"),
      rows: data.lowest_scores ?? [],
      showMargin: false,
    },
    {
      key: "win",
      title: t("ui.special.biggest_wins", "Höchste Siege"),
      rows: data.biggest_win_margin ?? [],
      showMargin: true,
    },
    {
      key: "loss",
      title: t("ui.special.biggest_losses", "Höchste Niederlagen"),
      rows: data.biggest_loss_margin ?? [],
      showMargin: true,
    },
  ];

  const hasAny = blocks.some((b) => b.rows.length > 0);
  if (!hasAny) {
    return (
      <p className="text-small text-muted p-4">
        {t("no_data", "Keine Daten verfügbar")}
      </p>
    );
  }

  return (
    <div className="grid gap-6 p-4 sm:grid-cols-2 lg:p-5">
      {blocks.map((block) => (
        <MiniTable
          key={block.key}
          title={block.title}
          rows={block.rows}
          teamName={teamName}
          showMargin={block.showMargin}
          t={t}
        />
      ))}
    </div>
  );
}

function MiniTable({
  title,
  rows,
  teamName,
  showMargin,
  t,
}: {
  title: string;
  rows: SpecialMatchRow[];
  teamName: string;
  showMargin: boolean;
  t: (key: string, fallback?: string) => string;
}) {
  const colSpan = showMargin ? 5 : 3;

  return (
    <div>
      <h3 className="text-h3 mb-2">{title}</h3>
      <table className="w-full border-collapse text-small">
        <thead>
          <tr className="border-b border-border text-muted">
            <th className="py-1.5 text-left font-medium">{t("score", "Ergebnis")}</th>
            {showMargin ? (
              <>
                <th className="py-1.5 text-left font-medium">
                  {t("ui.special.opponent_score", "Gegner Kegel")}
                </th>
                <th className="py-1.5 text-left font-medium">
                  {t("ui.special.margin", "Diff")}
                </th>
              </>
            ) : null}
            <th className="py-1.5 text-left font-medium">{t("event", "Ereignis")}</th>
            <th className="py-1.5 text-left font-medium">{t("opponent", "Gegner")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={colSpan} className="py-3 text-center text-muted">
                {t("no_data", "Keine Daten")}
              </td>
            </tr>
          ) : (
            rows.map((m, i) => (
              <SpecialMatchRowView
                key={i}
                match={m}
                teamName={teamName}
                showMargin={showMargin}
                t={t}
              />
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function SpecialMatchRowView({
  match,
  teamName,
  showMargin,
  t,
}: {
  match: SpecialMatchRow;
  teamName: string;
  showMargin: boolean;
  t: (key: string, fallback?: string) => string;
}) {
  const href = resolveSpecialMatchNavPath(match, teamName);
  const eventLabel = formatEvent(match);
  const rowClass = href
    ? "border-b border-border last:border-0 hover:bg-surface-subtle"
    : "border-b border-border last:border-0";
  const marginClass =
    (match.WinMargin ?? 0) > 0
      ? "text-success-fg"
      : (match.WinMargin ?? 0) < 0
        ? "text-danger-fg"
        : undefined;

  if (!href) {
    return (
      <tr className={rowClass}>
        <td className="py-2 font-mono font-semibold tabular-nums">{match.Score}</td>
        {showMargin ? (
          <>
            <td className="py-2 font-mono tabular-nums">{match.OpponentScore ?? "—"}</td>
            <td className={`py-2 font-mono tabular-nums ${marginClass ?? ""}`}>
              {formatMargin(match.WinMargin)}
            </td>
          </>
        ) : null}
        <td className="py-2">{eventLabel}</td>
        <td className="py-2 truncate" title={match.Opponent}>
          {match.Opponent}
        </td>
      </tr>
    );
  }

  const linkGrid = showMargin
    ? "grid grid-cols-[minmax(3rem,auto)_minmax(3rem,auto)_minmax(3rem,auto)_1fr_minmax(5rem,1fr)] gap-x-3 py-2 w-full text-inherit no-underline"
    : "grid grid-cols-[minmax(4rem,auto)_1fr_minmax(5rem,1fr)] gap-x-3 py-2 w-full text-inherit no-underline";

  return (
    <tr className={rowClass}>
      <td className="p-0" colSpan={showMargin ? 5 : 3}>
        <Link
          to={href}
          className={linkGrid}
          title={t("ui.special.open_matchday", "Spieltag in der Liga-Ansicht öffnen")}
        >
          <span className="font-mono font-semibold tabular-nums">{match.Score}</span>
          {showMargin ? (
            <>
              <span className="font-mono tabular-nums">{match.OpponentScore ?? "—"}</span>
              <span className={`font-mono tabular-nums ${marginClass ?? ""}`}>
                {formatMargin(match.WinMargin)}
              </span>
            </>
          ) : null}
          <span className="text-accent hover:underline">{eventLabel}</span>
          <span className="truncate" title={match.Opponent}>
            {match.Opponent}
          </span>
        </Link>
      </td>
    </tr>
  );
}
