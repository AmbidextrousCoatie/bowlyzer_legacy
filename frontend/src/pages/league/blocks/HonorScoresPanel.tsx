import { Link } from "react-router-dom";
import type { HonorScoreEntry, HonorScores } from "../../../hooks/useLeague";
import {
  resolveHonorScoreNavPath,
  type LeagueNavContext,
} from "../../../lib/leagueNavigation";

type Props = {
  honorScores: HonorScores | undefined;
  isPending?: boolean;
  isError?: boolean;
  t: (key: string, fallback?: string) => string;
  /** When set, each row links to league week + team (or game if round is on the entry). */
  navigation?: LeagueNavContext;
};

/** Renders the four honor-score lists (top scores, top team scores, best
 *  individual averages, best team averages) as hairline-separated rows.
 *  Empty groups are skipped. */
export function HonorScoresPanel({ honorScores, isPending, isError, t, navigation }: Props) {
  if (isPending) {
    return (
      <aside className="space-y-4">
        <p className="text-label uppercase text-muted">{t("honor_scores", "Bestleistungen")}</p>
        <div className="h-48 rounded-sm border border-border bg-surface-subtle" aria-hidden />
      </aside>
    );
  }
  if (isError) {
    return (
      <aside>
        <p className="text-label uppercase text-muted mb-3">
          {t("honor_scores", "Bestleistungen")}
        </p>
        <p className="text-small text-danger-fg">{t("error_loading_data", "Fehler beim Laden")}</p>
      </aside>
    );
  }
  if (!honorScores) return null;

  const groups: Array<{
    titleKey: string;
    titleFallback: string;
    entries: HonorScoreEntry[] | undefined;
    valueKey: "score" | "average";
  }> = [
    {
      titleKey: "top_individual_scores",
      titleFallback: "Top-Spieler-Scores",
      entries: honorScores.individual_scores,
      valueKey: "score",
    },
    {
      titleKey: "top_team_scores",
      titleFallback: "Top-Mannschafts-Scores",
      entries: honorScores.team_scores,
      valueKey: "score",
    },
    {
      titleKey: "best_individual_averages",
      titleFallback: "Beste Spieler-Schnitte",
      entries: honorScores.individual_averages,
      valueKey: "average",
    },
    {
      titleKey: "best_team_averages",
      titleFallback: "Beste Mannschafts-Schnitte",
      entries: honorScores.team_averages,
      valueKey: "average",
    },
  ];

  const visible = groups.filter((g) => Array.isArray(g.entries) && g.entries.length > 0);
  if (visible.length === 0) return null;

  return (
    <aside className="space-y-6">
      <p className="text-label uppercase text-muted">{t("honor_scores", "Bestleistungen")}</p>
      {visible.map((group) => (
        <div key={group.titleKey}>
          <p className="text-caption font-semibold text-foreground mb-2">
            {t(group.titleKey, group.titleFallback)}
          </p>
          <ul className="border-t border-border">
            {(group.entries ?? []).map((entry, idx) => (
              <HonorScoreRow
                key={idx}
                entry={entry}
                valueKey={group.valueKey}
                navigation={navigation}
              />
            ))}
          </ul>
        </div>
      ))}
    </aside>
  );
}

function HonorScoreRow({
  entry,
  valueKey,
  navigation,
}: {
  entry: HonorScoreEntry;
  valueKey: "score" | "average";
  navigation?: LeagueNavContext;
}) {
  const label = nameOf(entry);
  const value = valueOf(entry, valueKey);
  const to = navigation ? resolveHonorScoreNavPath(entry, navigation) : null;

  const rowClass =
    "flex items-baseline justify-between border-b border-border py-1.5 text-small";

  if (!to) {
    return (
      <li className={rowClass}>
        <span className="text-foreground">{label}</span>
        <span className="font-mono text-foreground">{value}</span>
      </li>
    );
  }

  return (
    <li>
      <Link
        to={to}
        className={
          rowClass +
          " text-foreground hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        }
      >
        <span className="hover:underline hover:underline-offset-2">{label}</span>
        <span className="font-mono">{value}</span>
      </Link>
    </li>
  );
}

function nameOf(entry: HonorScoreEntry): string {
  return entry.player ?? entry.player_name ?? entry.team ?? entry.team_name ?? entry.name ?? "—";
}

function valueOf(entry: HonorScoreEntry, preferred: "score" | "average"): string {
  if (preferred === "average") {
    if (typeof entry.average === "number") return entry.average.toFixed(1);
    if (entry.average !== undefined) return String(entry.average);
  }
  if (typeof entry.score === "number") return String(entry.score);
  if (entry.score !== undefined) return String(entry.score);
  if (entry.total_score !== undefined) return String(entry.total_score);
  if (entry.value !== undefined) return String(entry.value);
  return "—";
}
