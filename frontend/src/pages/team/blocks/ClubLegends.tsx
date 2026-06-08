import {
  Activity,
  Award,
  CalendarRange,
  Layers,
  Sparkles,
  TrendingUp,
  Users,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useClubLegends, type ClubLegendEntry } from "../../../hooks/useLeague";
import { buildUrl } from "../../../lib/api";
import { getPaletteColor } from "../../../lib/color-utils";

type Props = {
  club: string;
  t: (key: string, fallback?: string) => string;
};

type LegendCategory = {
  id: string;
  titleKey: string;
  titleFallback: string;
  icon: LucideIcon;
  entries?: ClubLegendEntry[];
  formatValue: (entry: ClubLegendEntry) => string;
  detail?: (entry: ClubLegendEntry) => string | undefined;
};

export function ClubLegends({ club, t }: Props) {
  const legendsQuery = useClubLegends(club);

  const loading = legendsQuery.isPending;
  const error = legendsQuery.isError;
  const data = legendsQuery.data;

  const categories: LegendCategory[] = data
    ? [
        {
          id: "most_seasons",
          titleKey: "ui.team.club_legends_most_seasons",
          titleFallback: "Meiste Saisons",
          icon: CalendarRange,
          entries: data.most_seasons,
          formatValue: (e) => String(e.value),
          detail: (e) =>
            t("ui.team.club_legends_seasons_count", "{n} Saisons").replace(
              "{n}",
              String(e.value),
            ),
        },
        {
          id: "most_games",
          titleKey: "ui.team.club_legends_most_games",
          titleFallback: "Meiste Spiele",
          icon: Activity,
          entries: data.most_games,
          formatValue: (e) => String(e.games ?? e.value),
          detail: (e) =>
            e.average != null
              ? `${e.games ?? e.value} ${t("ui.player.games", "Spiele")} · Ø ${formatAvg(e.average)}`
              : `${e.games ?? e.value} ${t("ui.player.games", "Spiele")}`,
        },
        {
          id: "highest_average",
          titleKey: "ui.team.club_legends_highest_avg",
          titleFallback: "Höchster Durchschnitt",
          icon: TrendingUp,
          entries: data.highest_average,
          formatValue: (e) => formatAvg(e.average ?? e.value),
          detail: (e) =>
            e.games != null
              ? `${e.games} ${t("ui.player.games", "Spiele")} · min. 12`
              : undefined,
        },
        {
          id: "best_seasons",
          titleKey: "ui.team.club_legends_best_seasons",
          titleFallback: "Beste Saisons",
          icon: Sparkles,
          entries: data.best_seasons,
          formatValue: (e) => formatAvg(e.average ?? e.value),
          detail: (e) =>
            [e.season, e.games != null ? `${e.games} ${t("ui.player.games", "Spiele")}` : null]
              .filter(Boolean)
              .join(" · "),
        },
        {
          id: "most_teams",
          titleKey: "ui.team.club_legends_most_teams",
          titleFallback: "Meiste Mannschaften",
          icon: Users,
          entries: data.most_teams_represented,
          formatValue: (e) => String(e.value),
          detail: (e) =>
            e.teams?.length
              ? `${t("ui.team.club_legends_teams_list", "Mannschaften")}: ${e.teams.join(", ")}`
              : undefined,
        },
        {
          id: "most_leagues",
          titleKey: "ui.team.club_legends_most_leagues",
          titleFallback: "Meiste Ligen",
          icon: Layers,
          entries: data.most_leagues_seen,
          formatValue: (e) => String(e.value),
          detail: (e) => (e.leagues?.length ? e.leagues.join(" · ") : undefined),
        },
      ]
    : [];

  const visibleCategories = categories.filter((cat) => cat.entries?.length);

  return (
    <section className="rounded-sm border border-border bg-surface">
      <header className="border-b border-border px-4 py-3 lg:px-5">
        <div className="flex items-start gap-2.5">
          <Award
            className="mt-0.5 h-5 w-5 shrink-0 text-accent"
            strokeWidth={1.75}
            aria-hidden
          />
          <div>
            <h2 className="text-h3">{t("ui.team.club_legends_heading", "Club-Legenden")}</h2>
            <p className="text-small text-muted mt-1">
              {t(
                "ui.team.club_legends_hint",
                "Spieler-Highlights für diesen Club — Liga-Spiele, alle Saisons.",
              )}
            </p>
          </div>
        </div>
      </header>

      {loading ? (
        <p className="text-small text-muted px-4 py-4 lg:px-5">
          {t("ui.team.club_legends_loading", "Club-Legenden werden geladen…")}
        </p>
      ) : error ? (
        <p className="text-small text-muted px-4 py-4 lg:px-5">
          {t("ui.team.club_legends_error", "Club-Legenden konnten nicht geladen werden.")}
        </p>
      ) : visibleCategories.length === 0 ? (
        <p className="text-small text-muted px-4 py-4 lg:px-5">
          {t("ui.team.club_legends_empty", "Keine Spielerdaten für diesen Club.")}
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-2 xl:grid-cols-3 lg:p-5">
          {visibleCategories.map((category, categoryIdx) => (
            <LegendCategoryBlock
              key={category.id}
              category={category}
              categoryIdx={categoryIdx}
              club={club}
              t={t}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function LegendCategoryBlock({
  category,
  categoryIdx,
  club,
  t,
}: {
  category: LegendCategory;
  categoryIdx: number;
  club: string;
  t: (key: string, fallback?: string) => string;
}) {
  const Icon = category.icon;
  const entries = category.entries ?? [];
  const accentColor = getPaletteColor(categoryIdx % 10);

  return (
    <div className="flex min-w-0 flex-col rounded-sm border border-border bg-surface px-3 py-4 sm:px-4">
      <div
        className="mb-3 flex min-w-0 items-start gap-2.5 border-b border-border border-l-4 pb-3 pl-2.5"
        style={{ borderLeftColor: accentColor }}
      >
        <span
          className="grid h-8 w-8 shrink-0 place-items-center rounded-sm border border-border"
          style={{ backgroundColor: `color-mix(in srgb, ${accentColor} 18%, transparent)` }}
        >
          <Icon className="h-4 w-4" style={{ color: accentColor }} strokeWidth={1.75} aria-hidden />
        </span>
        <h3 className="min-w-0 text-body font-semibold leading-snug text-foreground xl:text-h3">
          {t(category.titleKey, category.titleFallback)}
        </h3>
      </div>
      <ul className="border-t border-border">
        {entries.map((entry, idx) => (
          <li
            key={`${entry.player_id || entry.player_name}-${idx}`}
            className={
              "flex items-center gap-2.5 border-b border-border py-2.5 text-small sm:gap-3 " +
              (idx === 0 ? "bg-accent-tint/40" : "")
            }
          >
            <RankBadge rank={idx + 1} />
            <div className="min-w-0 flex-1">
              <Link
                to={buildUrl("/spieler", {
                  club,
                  player_name: entry.player_name,
                  player_id: entry.player_id || undefined,
                })}
                className="block truncate font-medium text-foreground hover:text-accent hover:underline"
                title={entry.player_name}
              >
                {entry.player_name}
              </Link>
              {category.detail?.(entry) ? (
                <p
                  className="text-label text-muted mt-0.5 truncate"
                  title={category.detail(entry)}
                >
                  {category.detail(entry)}
                </p>
              ) : null}
            </div>
            <span
              className="shrink-0 font-mono text-small font-semibold tabular-nums text-foreground sm:text-base"
              title={category.formatValue(entry)}
            >
              {category.formatValue(entry)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Flat-left / rounded-right rank clip — palette index matches place (1→0, 2→1, …). */
function RankBadge({ rank }: { rank: number }) {
  const color = getPaletteColor(rank - 1);

  return (
    <span
      className="inline-flex h-6 min-w-[1.75rem] shrink-0 items-center justify-center rounded-r-full pl-1.5 pr-2 font-mono text-[11px] font-semibold tabular-nums leading-none text-white"
      style={{
        backgroundColor: color,
        boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${color} 70%, black 30%)`,
      }}
      aria-hidden
    >
      {rank}
    </span>
  );
}

function formatAvg(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : "—";
}
