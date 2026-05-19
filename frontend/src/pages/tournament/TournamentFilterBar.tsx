import { useMemo, useState } from "react";
import { ChevronDown, Menu } from "lucide-react";
import { BottomSheet } from "../../components/BottomSheet";
import { PlayerSearch } from "../../components/PlayerSearch";
import type { TournamentRound } from "../../hooks/useTournament";
import { useMobileNav } from "../../context/MobileNavContext";

export type TournamentFilterBarProps = {
  season: string;
  seasons: string[];
  seasonsLoading: boolean;
  tournament: string;
  tournaments: string[];
  tournamentsLoading: boolean;
  round: string;
  rounds: TournamentRound[];
  roundsLoading: boolean;
  player: string;
  players: string[];
  playersLoading: boolean;
  playerMode: boolean;
  onSeasonChange: (v: string) => void;
  onTournamentChange: (v: string) => void;
  onRoundChange: (v: string) => void;
  onPlayerChange: (v: string) => void;
  t: (key: string, fallback?: string) => string;
  pageHeading: string;
};

export function TournamentFilterBar(props: TournamentFilterBarProps) {
  return (
    <>
      <FilterRailDesktop {...props} />
      <FilterBarMobile {...props} />
    </>
  );
}

function FilterRailDesktop(props: TournamentFilterBarProps) {
  const { t } = props;
  const playerEntries = usePlayerEntries(props.players);
  const playerSearchDisabled =
    props.playersLoading || !props.season || !props.tournament;

  return (
    <div className="sticky top-0 z-10 -mx-4 hidden border-b border-border bg-background/85 px-4 py-3 backdrop-blur lg:-mx-8 lg:block lg:px-8">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <SeasonTournamentFields {...props} selectClassName="h-9 min-w-[160px] text-small" />
        {!props.playerMode && (
          <FilterField label={t("ui.tournament.round", "Runde")}>
            <SelectControl
              value={props.round}
              onChange={props.onRoundChange}
              disabled={props.roundsLoading}
              ariaLabel={t("ui.tournament.round", "Runde")}
              className="h-9 min-w-[160px] text-small"
            >
              <option value="">{t("ui.tournament.all_latest", "Gesamt")}</option>
              {props.rounds.map((r) => (
                <option
                  key={String(r.round_number)}
                  value={String(r.round_number)}
                  title={r.round_name ? String(r.round_name) : undefined}
                >
                  {r.round_number}
                </option>
              ))}
            </SelectControl>
          </FilterField>
        )}
        <FilterField label={t("ui.tournament.player", "Spieler")}>
          <PlayerSearch
            value={props.player}
            players={playerEntries}
            isLoading={playerSearchDisabled}
            placeholder={t("ui.tournament.player_search_placeholder", "Spieler suchen…")}
            ariaLabel={t("ui.tournament.player", "Spieler")}
            clearAriaLabel={t("ui.tournament.clear_player", "Spieler-Auswahl löschen")}
            onSelect={(entry) => props.onPlayerChange(entry?.name ?? "")}
          />
        </FilterField>
      </div>
    </div>
  );
}

function FilterBarMobile(props: TournamentFilterBarProps) {
  const { t } = props;
  const { openMobileNav } = useMobileNav();
  const [sheetOpen, setSheetOpen] = useState(false);
  const hasTournament = !!props.tournament;
  const hasDrillDown = props.playerMode
    ? !!props.player
    : !!(props.round || props.player);

  const playerEntries = usePlayerEntries(props.players);
  const playerSearchDisabled =
    props.playersLoading || !props.season || !props.tournament;
  const summary = buildDrillDownSummary(props, t);

  const moreFiltersButton = (
    <button
      type="button"
      onClick={() => setSheetOpen(true)}
      className="flex h-9 shrink-0 items-center justify-between gap-1.5 rounded-sm border border-border bg-surface px-2.5 text-small font-medium text-foreground hover:border-border-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring max-lg:landscape:h-8 max-lg:landscape:px-2 max-lg:landscape:text-[13px]"
    >
      <span className="max-lg:landscape:hidden">{t("more_filters", "Weitere Auswahl")}</span>
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
      <div className="@container/tournament-bar sticky top-0 z-20 -mx-4 hidden min-w-0 border-b border-border bg-background/85 px-3 py-2 backdrop-blur max-lg:landscape:flex max-lg:landscape:items-center max-lg:landscape:gap-2 lg:hidden">
        <button
          type="button"
          aria-label="Menü öffnen"
          onClick={openMobileNav}
          className="grid h-8 w-8 shrink-0 place-items-center rounded-sm text-muted hover:bg-surface-subtle hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <Menu size={18} strokeWidth={1.75} />
        </button>
        <div
          title={props.pageHeading}
          className="flex min-w-0 shrink-[1000] items-center overflow-hidden @max-[14rem]/tournament-bar:pointer-events-none @max-[14rem]/tournament-bar:max-w-0 @max-[14rem]/tournament-bar:opacity-0"
        >
          <span className="min-w-0 shrink truncate text-small font-semibold leading-tight text-foreground">
            {props.pageHeading}
          </span>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <CompactSeasonTournamentFields {...props} />
          {hasTournament && moreFiltersButton}
        </div>
      </div>

      <div className="sticky top-0 z-10 -mx-4 border-b border-border bg-background/85 px-4 py-3 backdrop-blur max-lg:landscape:hidden lg:hidden">
        <div className="grid grid-cols-2 gap-3">
          <SeasonTournamentFields
            {...props}
            selectClassName="h-11 w-full min-w-0 text-[15px]"
          />
        </div>

        {hasTournament && (
          <div className="mt-3 space-y-2">
            {hasDrillDown && (
              <p className="text-small text-muted leading-snug">{summary}</p>
            )}
            <button
              type="button"
              onClick={() => setSheetOpen(true)}
              className="flex h-11 w-full items-center justify-between gap-2 rounded-sm border border-border bg-surface px-3 text-[15px] font-medium text-foreground hover:border-border-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              <span>{t("more_filters", "Weitere Auswahl")}</span>
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
        title={t("more_filters", "Weitere Auswahl")}
        closeLabel={t("done", "Fertig")}
      >
        <div className="space-y-4">
          {!props.playerMode && (
            <FilterField label={t("ui.tournament.round", "Runde")}>
              <SelectControl
                value={props.round}
                onChange={props.onRoundChange}
                disabled={props.roundsLoading}
                ariaLabel={t("ui.tournament.round", "Runde")}
                className="h-11 w-full text-[15px]"
              >
                <option value="">{t("ui.tournament.all_latest", "Gesamt")}</option>
                {props.rounds.map((r) => (
                  <option
                    key={String(r.round_number)}
                    value={String(r.round_number)}
                    title={r.round_name ? String(r.round_name) : undefined}
                  >
                    {r.round_number}
                  </option>
                ))}
              </SelectControl>
            </FilterField>
          )}

          <FilterField label={t("ui.tournament.player", "Spieler")}>
            <div className="w-full min-w-0 [&_input]:h-11 [&_input]:text-[15px]">
              <PlayerSearch
                value={props.player}
                players={playerEntries}
                isLoading={playerSearchDisabled}
                placeholder={t("ui.tournament.player_search_placeholder", "Spieler suchen…")}
                ariaLabel={t("ui.tournament.player", "Spieler")}
                clearAriaLabel={t("ui.tournament.clear_player", "Spieler-Auswahl löschen")}
                onSelect={(entry) => props.onPlayerChange(entry?.name ?? "")}
              />
            </div>
          </FilterField>
        </div>
      </BottomSheet>
    </>
  );
}

function CompactSeasonTournamentFields(
  props: Pick<
    TournamentFilterBarProps,
    | "season"
    | "seasons"
    | "seasonsLoading"
    | "tournament"
    | "tournaments"
    | "tournamentsLoading"
    | "onSeasonChange"
    | "onTournamentChange"
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
        ariaLabel={t("ui.tournament.season", "Saison")}
        className={selectClass}
      >
        <option value="">—</option>
        {props.seasons.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </SelectControl>
      <SelectControl
        value={props.tournament}
        onChange={props.onTournamentChange}
        disabled={props.tournamentsLoading}
        ariaLabel={t("ui.tournament.tournament", "Turnier")}
        className={selectClass}
      >
        <option value="">—</option>
        {props.tournaments.map((tn) => (
          <option key={tn} value={tn}>
            {tn}
          </option>
        ))}
      </SelectControl>
    </>
  );
}

function SeasonTournamentFields({
  season,
  seasons,
  seasonsLoading,
  tournament,
  tournaments,
  tournamentsLoading,
  onSeasonChange,
  onTournamentChange,
  t,
  selectClassName,
}: Pick<
  TournamentFilterBarProps,
  | "season"
  | "seasons"
  | "seasonsLoading"
  | "tournament"
  | "tournaments"
  | "tournamentsLoading"
  | "onSeasonChange"
  | "onTournamentChange"
  | "t"
> & { selectClassName: string }) {
  return (
    <>
      <FilterField label={t("ui.tournament.season", "Saison")}>
        <SelectControl
          value={season}
          onChange={onSeasonChange}
          disabled={seasonsLoading}
          ariaLabel={t("ui.tournament.season", "Saison")}
          className={selectClassName}
        >
          <option value="">—</option>
          {seasons.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </SelectControl>
      </FilterField>
      <FilterField label={t("ui.tournament.tournament", "Turnier")}>
        <SelectControl
          value={tournament}
          onChange={onTournamentChange}
          disabled={tournamentsLoading}
          ariaLabel={t("ui.tournament.tournament", "Turnier")}
          className={selectClassName}
        >
          <option value="">—</option>
          {tournaments.map((tn) => (
            <option key={tn} value={tn}>
              {tn}
            </option>
          ))}
        </SelectControl>
      </FilterField>
    </>
  );
}

function buildDrillDownSummary(
  props: TournamentFilterBarProps,
  t: TournamentFilterBarProps["t"],
): string {
  const parts: string[] = [];
  if (!props.playerMode && props.round) {
    parts.push(roundLabel(props.round, props.rounds, t));
  }
  if (props.player) {
    parts.push(props.player);
  }
  return parts.join(" · ");
}

function roundLabel(
  round: string,
  rounds: TournamentRound[],
  t: TournamentFilterBarProps["t"],
): string {
  const found = rounds.find((r) => String(r.round_number) === round);
  if (found?.round_name) return String(found.round_name);
  return `${t("ui.tournament.round", "Runde")} ${round}`;
}

function usePlayerEntries(players: string[]) {
  return useMemo(() => players.map((name) => ({ id: name, name })), [players]);
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
