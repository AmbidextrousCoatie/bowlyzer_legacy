import { useState } from "react";
import { ChevronDown, Menu } from "lucide-react";
import { BottomSheet } from "../../components/BottomSheet";
import { useMobileNav } from "../../context/MobileNavContext";
import { LEAGUE_SEASON_ALL, LEAGUE_SEASON_LATEST } from "../../lib/leagueSeason";

export type LeagueFilterBarProps = {
  season: string;
  seasons: string[];
  seasonsLoading: boolean;
  league: string;
  leagues: { short_name: string; long_name: string; value: string }[];
  leaguesLoading: boolean;
  week: string;
  weeks: number[];
  weeksLoading: boolean;
  team: string;
  teams: string[];
  teamsLoading: boolean;
  round: string;
  rounds: number[];
  roundsLoading: boolean;
  onSeasonChange: (v: string) => void;
  onLeagueChange: (v: string) => void;
  onWeekChange: (v: string) => void;
  onTeamChange: (v: string) => void;
  onRoundChange: (v: string) => void;
  t: (key: string, fallback?: string) => string;
  /** App label (portrait header eyebrow), e.g. "Bowl-A-Lyzer". */
  pageName: string;
  /** Page heading for landscape compact chrome, e.g. "Liga · Saison 25/26". */
  pageHeading: string;
};

export function LeagueFilterBar(props: LeagueFilterBarProps) {
  return (
    <>
      <FilterRailDesktop {...props} />
      <FilterBarMobile {...props} />
    </>
  );
}

function FilterRailDesktop(props: LeagueFilterBarProps) {
  const { t } = props;
  const showWeek = !!props.league;
  const showTeam = !!props.league;
  const showRound = !!props.week;

  return (
    <div className="sticky top-0 z-10 -mx-4 hidden border-b border-border bg-background/85 px-4 py-3 backdrop-blur lg:-mx-8 lg:block lg:px-8">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <SeasonLeagueFields {...props} selectClassName="h-9 min-w-[160px] text-small" />
        {showWeek && (
          <FilterField label={t("week", "Spieltag")}>
            <SelectControl
              value={props.week}
              onChange={props.onWeekChange}
              disabled={props.weeksLoading}
              ariaLabel={t("week", "Spieltag")}
              className="h-9 min-w-[160px] text-small"
            >
              <option value="">{t("week_all", "Alle Spieltage")}</option>
              {props.weeks.map((w) => (
                <option key={w} value={String(w)}>
                  {w}
                </option>
              ))}
            </SelectControl>
          </FilterField>
        )}
        {showTeam && (
          <FilterField label={t("team", "Mannschaft")}>
            <SelectControl
              value={props.team}
              onChange={props.onTeamChange}
              disabled={props.teamsLoading}
              ariaLabel={t("team", "Mannschaft")}
              className="h-9 min-w-[160px] text-small"
            >
              <option value="">{t("team_all", "Alle Mannschaften")}</option>
              {props.teams.map((tm) => (
                <option key={tm} value={tm}>
                  {tm}
                </option>
              ))}
            </SelectControl>
          </FilterField>
        )}
        {showRound && (
          <FilterField label={t("game", "Spiel")}>
            <SelectControl
              value={props.round}
              onChange={props.onRoundChange}
              disabled={props.roundsLoading}
              ariaLabel={t("game", "Spiel")}
              className="h-9 min-w-[160px] text-small"
            >
              <option value="">{t("game_all", "Alle Spiele")}</option>
              {props.rounds.map((r) => (
                <option key={r} value={String(r)}>
                  {r}
                </option>
              ))}
            </SelectControl>
          </FilterField>
        )}
      </div>
    </div>
  );
}

function FilterBarMobile(props: LeagueFilterBarProps) {
  const { t } = props;
  const { openMobileNav } = useMobileNav();
  const [sheetOpen, setSheetOpen] = useState(false);
  const hasLeague = !!props.league;
  const hasDrillDown = !!(props.week || props.team || props.round);

  const summary = buildDrillDownSummary(props, t);
  const moreFiltersButton = (
    <button
      type="button"
      onClick={() => setSheetOpen(true)}
      className="flex h-9 shrink-0 items-center justify-between gap-1.5 rounded-sm border border-border bg-surface px-2.5 text-small font-medium text-foreground hover:border-border-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring max-lg:landscape:h-8 max-lg:landscape:px-2 max-lg:landscape:text-[13px]"
    >
      <span className="max-lg:landscape:hidden">{t("more_filters", "Auswahl anpassen")}</span>
      <span className="hidden max-lg:landscape:inline">{t("more_filters_short", "Mehr")}</span>
      <span className="flex items-center gap-1 text-muted">
        {hasDrillDown && (
          <span className="rounded-xs bg-accent-tint px-1 py-0.5 text-[10px] font-semibold uppercase leading-none text-accent">
            {t("filters_active", "Aktiv")}
          </span>
        )}
        <ChevronDown size={16} strokeWidth={1.75} aria-hidden className="max-lg:landscape:size-[14px]" />
      </span>
    </button>
  );

  return (
  <>
    {/* Landscape phone/tablet: one row — menu, title, Saison/Liga, Mehr */}
    <div className="@container/league-bar sticky top-0 z-20 -mx-4 hidden min-w-0 border-b border-border bg-background/85 px-3 py-2 backdrop-blur max-lg:landscape:flex max-lg:landscape:items-center max-lg:landscape:gap-2 lg:hidden">
      <button
        type="button"
        aria-label="Menü öffnen"
        onClick={openMobileNav}
        className="grid h-8 w-8 shrink-0 place-items-center rounded-sm text-muted hover:bg-surface-subtle hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        <Menu size={18} strokeWidth={1.75} />
      </button>
      <div
        title={`${props.pageName} · ${props.pageHeading}`}
        className="flex min-w-0 shrink-[1000] items-center gap-1.5 overflow-hidden @max-[22rem]/league-bar:pointer-events-none @max-[22rem]/league-bar:max-w-0 @max-[22rem]/league-bar:opacity-0"
      >
        <span className="min-w-0 shrink-[2000] truncate text-[11px] font-medium uppercase tracking-wide text-muted @max-[30rem]/league-bar:max-w-0 @max-[30rem]/league-bar:opacity-0">
          {props.pageName}
        </span>
        <span
          className="shrink-0 text-muted/50 @max-[30rem]/league-bar:hidden"
          aria-hidden
        >
          ·
        </span>
        <span className="min-w-0 shrink truncate text-small font-semibold leading-tight text-foreground">
          {props.pageHeading}
        </span>
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-2">
        <CompactSeasonLeagueFields {...props} />
        {hasLeague && moreFiltersButton}
      </div>
    </div>

    {/* Portrait mobile: Saison/Liga grid + Auswahl anpassen */}
    <div className="sticky top-0 z-10 -mx-4 border-b border-border bg-background/85 px-4 py-3 backdrop-blur max-lg:landscape:hidden lg:hidden">
      <div className="grid grid-cols-2 gap-3">
        <SeasonLeagueFields
          {...props}
          selectClassName="h-11 w-full min-w-0 text-[15px]"
        />
      </div>

      {hasLeague && (
        <div className="mt-3 space-y-2">
          {hasDrillDown && (
            <p className="text-small text-muted leading-snug">{summary}</p>
          )}
          <button
            type="button"
            onClick={() => setSheetOpen(true)}
            className="flex h-11 w-full items-center justify-between gap-2 rounded-sm border border-border bg-surface px-3 text-[15px] font-medium text-foreground hover:border-border-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            <span>{t("more_filters", "Auswahl anpassen")}</span>
            <span className="flex items-center gap-2 text-muted">
              {hasDrillDown && (
                <span className="rounded-xs bg-accent-tint px-1.5 py-0.5 text-label uppercase text-accent">
                  {t("filters_active", "Aktiv")}
                </span>
              )}
              <ChevronDown size={18} strokeWidth={1.75} aria-hidden />
            </span>
          </button>
        </div>
      )}
    </div>

    <BottomSheet
      open={sheetOpen}
      onClose={() => setSheetOpen(false)}
      title={t("more_filters", "Auswahl anpassen")}
      closeLabel={t("done", "Fertig")}
    >
      <div className="space-y-4">
        <FilterField label={t("week", "Spieltag")}>
          <SelectControl
            value={props.week}
            onChange={props.onWeekChange}
            disabled={props.weeksLoading}
            ariaLabel={t("week", "Spieltag")}
            className="h-11 w-full text-[15px]"
          >
            <option value="">{t("week_all", "Alle Spieltage")}</option>
            {props.weeks.map((w) => (
              <option key={w} value={String(w)}>
                {w}
              </option>
            ))}
          </SelectControl>
        </FilterField>

        <FilterField label={t("team", "Mannschaft")}>
          <SelectControl
            value={props.team}
            onChange={props.onTeamChange}
            disabled={props.teamsLoading}
            ariaLabel={t("team", "Mannschaft")}
            className="h-11 w-full text-[15px]"
          >
            <option value="">{t("team_all", "Alle Mannschaften")}</option>
            {props.teams.map((tm) => (
              <option key={tm} value={tm}>
                {tm}
              </option>
            ))}
          </SelectControl>
        </FilterField>

        {!!props.week && (
          <FilterField label={t("game", "Spiel")}>
            <SelectControl
              value={props.round}
              onChange={props.onRoundChange}
              disabled={props.roundsLoading}
              ariaLabel={t("game", "Spiel")}
              className="h-11 w-full text-[15px]"
            >
              <option value="">{t("game_all", "Alle Spiele")}</option>
              {props.rounds.map((r) => (
                <option key={r} value={String(r)}>
                  {r}
                </option>
              ))}
            </SelectControl>
          </FilterField>
        )}
      </div>
    </BottomSheet>
  </>
  );
}

function CompactSeasonLeagueFields(
  props: Pick<
    LeagueFilterBarProps,
    | "season"
    | "seasons"
    | "seasonsLoading"
    | "league"
    | "leagues"
    | "leaguesLoading"
    | "onSeasonChange"
    | "onLeagueChange"
    | "t"
  >,
) {
  const { t } = props;
  const selectClass =
    "h-8 w-[min(7.5rem,24vw)] min-w-[4.25rem] shrink-0 rounded-sm border border-border bg-surface px-2 text-[13px] text-foreground hover:border-border-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60";
  return (
    <>
      <SelectControl
        value={props.season}
        onChange={props.onSeasonChange}
        disabled={props.seasonsLoading}
        ariaLabel={t("season", "Saison")}
        className={selectClass}
      >
        <option value={LEAGUE_SEASON_LATEST}>{t("season_latest", "Aktuelle Saison")}</option>
        <option value={LEAGUE_SEASON_ALL}>{t("season_all", "Alle Saisons")}</option>
        {props.seasons.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </SelectControl>
      <SelectControl
        value={props.league}
        onChange={props.onLeagueChange}
        disabled={props.leaguesLoading}
        ariaLabel={t("league", "Liga")}
        className={selectClass}
      >
        <option value="">{t("league_all", "Alle Ligen")}</option>
        {props.leagues.map((l) => (
          <option key={l.value} value={l.value}>
            {l.long_name || l.short_name}
          </option>
        ))}
      </SelectControl>
    </>
  );
}

function SeasonLeagueFields({
  season,
  seasons,
  seasonsLoading,
  league,
  leagues,
  leaguesLoading,
  onSeasonChange,
  onLeagueChange,
  t,
  selectClassName,
}: Pick<
  LeagueFilterBarProps,
  | "season"
  | "seasons"
  | "seasonsLoading"
  | "league"
  | "leagues"
  | "leaguesLoading"
  | "onSeasonChange"
  | "onLeagueChange"
  | "t"
> & { selectClassName: string }) {
  return (
    <>
      <FilterField label={t("season", "Saison")}>
        <SelectControl
          value={season}
          onChange={onSeasonChange}
          disabled={seasonsLoading}
          ariaLabel={t("season", "Saison")}
          className={selectClassName}
        >
          <option value={LEAGUE_SEASON_LATEST}>{t("season_latest", "Aktuelle Saison")}</option>
          <option value={LEAGUE_SEASON_ALL}>{t("season_all", "Alle Saisons")}</option>
          {seasons.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </SelectControl>
      </FilterField>
      <FilterField label={t("league", "Liga")}>
        <SelectControl
          value={league}
          onChange={onLeagueChange}
          disabled={leaguesLoading}
          ariaLabel={t("league", "Liga")}
          className={selectClassName}
        >
          <option value="">{t("league_all", "Alle Ligen")}</option>
          {leagues.map((l) => (
            <option key={l.value} value={l.value}>
              {l.long_name || l.short_name}
            </option>
          ))}
        </SelectControl>
      </FilterField>
    </>
  );
}

function buildDrillDownSummary(props: LeagueFilterBarProps, t: LeagueFilterBarProps["t"]): string {
  const parts: string[] = [];
  if (props.week) {
    parts.push(`${t("week", "Spieltag")} ${props.week}`);
  }
  if (props.team) {
    parts.push(props.team);
  }
  if (props.round) {
    parts.push(`${t("game", "Spiel")} ${props.round}`);
  }
  return parts.join(" · ");
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-label uppercase text-muted">{label}</span>
      {children}
    </label>
  );
}

function SelectControl({
  value,
  onChange,
  disabled,
  ariaLabel,
  className,
  children,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  ariaLabel: string;
  className: string;
  children: React.ReactNode;
}) {
  return (
    <select
      aria-label={ariaLabel}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className={
        "rounded-sm border border-border bg-surface px-2.5 text-foreground hover:border-border-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60 " +
        className
      }
    >
      {children}
    </select>
  );
}
