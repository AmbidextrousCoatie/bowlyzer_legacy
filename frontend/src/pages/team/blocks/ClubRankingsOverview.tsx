import {
  Award,
  CalendarRange,
  Crown,
  Hash,
  Target,
  Trophy,
  Users,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";
import {
  useClubRankings,
  type ClubRankingEntry,
  type ClubRankingsPayload,
} from "../../../hooks/useLeague";
import { buildUrl } from "../../../lib/api";
import { getPaletteColor } from "../../../lib/color-utils";
import { teamDisplayLabel } from "../../../lib/teamUtils";

type Props = {
  t: (key: string, fallback?: string) => string;
};

type RankingCategory = {
  id: keyof Omit<ClubRankingsPayload, "top_n">;
  titleKey: string;
  titleFallback: string;
  icon: LucideIcon;
  entries?: ClubRankingEntry[];
  formatValue: (entry: ClubRankingEntry) => string;
  headline?: (entry: ClubRankingEntry) => string;
  detail?: (entry: ClubRankingEntry) => string | undefined;
  linkFor?: (entry: ClubRankingEntry) => string;
};

export function ClubRankingsOverview({ t }: Props) {
  const rankingsQuery = useClubRankings();
  const loading = rankingsQuery.isPending;
  const error = rankingsQuery.isError;
  const data = rankingsQuery.data;

  const categories: RankingCategory[] = data
    ? [
        {
          id: "highest_total_pinfall",
          titleKey: "ui.team.club_rankings_highest_total_pinfall",
          titleFallback: "Höchster Gesamtpinfall",
          icon: Hash,
          entries: data.highest_total_pinfall,
          formatValue: (e) => formatCount(e.value),
        },
        {
          id: "most_members",
          titleKey: "ui.team.club_rankings_most_members",
          titleFallback: "Meiste Mitglieder",
          icon: Users,
          entries: data.most_members,
          formatValue: (e) => formatCount(e.value),
        },
        {
          id: "highest_weekly_team_average",
          titleKey: "ui.team.club_rankings_highest_weekly_team_average",
          titleFallback: "Höchster Spieltagsschnitt",
          icon: CalendarRange,
          entries: data.highest_weekly_team_average,
          formatValue: (e) => formatAverage(e.value),
          headline: (e) => formatEventHeadline(e, t),
          detail: (e) => formatEventContext(e, t),
          linkFor: (e) => buildLigaWeekLink(e),
        },
        {
          id: "highest_team_game_average",
          titleKey: "ui.team.club_rankings_highest_team_game_average",
          titleFallback: "Höchstes Mannschaftsspiel",
          icon: Target,
          entries: data.highest_team_game_average,
          formatValue: (e) => formatAverage(e.value),
          headline: (e) => formatEventHeadline(e, t),
          detail: (e) => formatMatchContext(e, t),
          linkFor: (e) => buildLigaMatchLink(e),
        },
        {
          id: "most_tournament_wins",
          titleKey: "ui.team.club_rankings_most_tournament_wins",
          titleFallback: "Meiste Turniersiege",
          icon: Trophy,
          entries: data.most_tournament_wins,
          formatValue: (e) => formatCount(e.value),
        },
        {
          id: "most_league_wins",
          titleKey: "ui.team.club_rankings_most_league_wins",
          titleFallback: "Meiste Ligasiege",
          icon: Crown,
          entries: data.most_league_wins,
          formatValue: (e) => formatCount(e.value),
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
            <h2 className="text-h3">{t("ui.team.club_rankings_heading", "Club-Ranglisten")}</h2>
            <p className="text-small text-muted mt-1">
              {t(
                "ui.team.club_rankings_hint",
                "Top-Clubs in der Datenquelle — wähle oben einen Club für Details.",
              )}
            </p>
          </div>
        </div>
      </header>

      {loading ? (
        <p className="text-small text-muted px-4 py-4 lg:px-5">
          {t("ui.team.club_rankings_loading", "Club-Ranglisten werden geladen…")}
        </p>
      ) : error ? (
        <p className="text-small text-muted px-4 py-4 lg:px-5">
          {t("ui.team.club_rankings_error", "Club-Ranglisten konnten nicht geladen werden.")}
        </p>
      ) : visibleCategories.length === 0 ? (
        <p className="text-small text-muted px-4 py-4 lg:px-5">
          {t("ui.team.club_rankings_empty", "Keine Club-Ranglisten verfügbar.")}
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-2 xl:grid-cols-3 lg:p-5">
          {visibleCategories.map((category, categoryIdx) => (
            <RankingCategoryBlock
              key={category.id}
              category={category}
              categoryIdx={categoryIdx}
              t={t}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function RankingCategoryBlock({
  category,
  categoryIdx,
  t,
}: {
  category: RankingCategory;
  categoryIdx: number;
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
        {entries.map((entry, idx) => {
          const headline = category.headline?.(entry) ?? entry.club;
          const href = category.linkFor?.(entry) ?? buildUrl("/club", { club: entry.club });
          const detail = category.detail?.(entry);
          return (
            <li
              key={`${entry.club}-${entry.team ?? ""}-${idx}`}
              className={
                "flex items-center gap-2.5 border-b border-border py-2.5 text-small sm:gap-3 " +
                (idx === 0 ? "bg-accent-tint/40" : "")
              }
            >
              <RankBadge rank={idx + 1} />
              <div className="min-w-0 flex-1">
                <Link
                  to={href}
                  className="block truncate font-medium text-foreground hover:text-accent hover:underline"
                  title={headline}
                >
                  {headline}
                </Link>
                {detail ? (
                  <p className="text-label text-muted mt-0.5 truncate" title={detail}>
                    {detail}
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
          );
        })}
      </ul>
    </div>
  );
}

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

function formatCount(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return value.toLocaleString("de-DE");
}

function formatAverage(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return value.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatEventHeadline(
  entry: ClubRankingEntry,
  t: (key: string, fallback?: string) => string,
): string {
  const teamLabel = entry.team ? teamDisplayLabel(entry.team) : "";
  if (!teamLabel || teamLabel === "Basis") return entry.club;
  return t("ui.team.club_rankings_headline_team", "{club} · {team}")
    .replace("{club}", entry.club)
    .replace("{team}", teamLabel);
}

function formatEventContext(
  entry: ClubRankingEntry,
  t: (key: string, fallback?: string) => string,
): string | undefined {
  if (!entry.season || !entry.league || !entry.week) return undefined;
  return t("ui.team.club_rankings_event_context", "{season} · {league} · W{week}")
    .replace("{season}", entry.season)
    .replace("{league}", entry.league)
    .replace("{week}", entry.week);
}

function formatMatchContext(
  entry: ClubRankingEntry,
  t: (key: string, fallback?: string) => string,
): string | undefined {
  if (!entry.season || !entry.league || !entry.week || !entry.round) return undefined;
  const total =
    entry.match_total != null && Number.isFinite(entry.match_total)
      ? formatCount(entry.match_total)
      : "—";
  return t(
    "ui.team.club_rankings_match_context",
    "{total} Kegel · {season} · {league} · W{week} · Spiel {round}",
  )
    .replace("{total}", total)
    .replace("{season}", entry.season)
    .replace("{league}", entry.league)
    .replace("{week}", entry.week)
    .replace("{round}", entry.round);
}

function buildLigaWeekLink(entry: ClubRankingEntry): string {
  if (!entry.season || !entry.league || !entry.week || !entry.team) {
    return buildUrl("/club", { club: entry.club });
  }
  return buildUrl("/liga", {
    season: entry.season,
    league: entry.league,
    week: entry.week,
    team: entry.team,
  });
}

function buildLigaMatchLink(entry: ClubRankingEntry): string {
  if (!entry.season || !entry.league || !entry.week || !entry.team || !entry.round) {
    return buildLigaWeekLink(entry);
  }
  return buildUrl("/liga", {
    season: entry.season,
    league: entry.league,
    week: entry.week,
    team: entry.team,
    round: entry.round,
  });
}
