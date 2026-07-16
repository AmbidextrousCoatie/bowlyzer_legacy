import { useEffect, useMemo, useState } from "react";
import { ChevronDown, Info, Menu, X } from "lucide-react";
import type { UseQueryResult } from "@tanstack/react-query";
import { BottomSheet } from "../../components/BottomSheet";
import { PlayerSearch } from "../../components/PlayerSearch";
import {
  EMPTY_TOURNAMENT_HANDICAP_FORMAT,
  useTournamentFormat,
  type HandicapFormatBand,
  type TournamentFormatInfo,
  type TournamentRound,
} from "../../hooks/useTournament";
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
  showEventDetail: boolean;
  onSeasonChange: (v: string) => void;
  onTournamentChange: (v: string) => void;
  onRoundChange: (v: string) => void;
  onPlayerChange: (v: string) => void;
  t: (key: string, fallback?: string) => string;
  pageHeading: string;
};

export function TournamentFilterBar(props: TournamentFilterBarProps) {
  const formatQuery = useTournamentFormat(
    props.showEventDetail ? props.season || null : null,
    props.showEventDetail ? props.tournament || null : null,
  );
  const [formatOpen, setFormatOpen] = useState(false);

  const formatTrigger = (
    <FormatInfoIconButton
      disabled={!props.showEventDetail || props.tournament === "" || formatQuery.isFetching}
      ariaLabel={props.t("ui.tournament.format_info_aria", "Turnierformat anzeigen")}
      onClick={() => setFormatOpen(true)}
    />
  );

  return (
    <>
      <FilterRailDesktop {...props} formatTrigger={formatTrigger} />
      <FilterBarMobile {...props} formatTrigger={formatTrigger} />
      <TournamentFormatModal
        open={formatOpen}
        onClose={() => setFormatOpen(false)}
        t={props.t}
        query={formatQuery}
      />
    </>
  );
}

type FormatTriggerProps = {
  formatTrigger: React.ReactNode;
};

function FilterRailDesktop(props: TournamentFilterBarProps & FormatTriggerProps) {
  const { t } = props;
  const playerEntries = usePlayerEntries(props.players);
  const playerSearchDisabled = props.playersLoading;

  return (
    <div className="sticky top-0 z-10 -mx-4 hidden border-b border-border bg-background/85 px-4 py-3 backdrop-blur lg:-mx-8 lg:block lg:px-8">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <SeasonTournamentFields
          {...props}
          selectClassName="h-9 min-w-[160px] text-small"
          tournamentInfoExtra={props.showEventDetail ? props.formatTrigger : null}
        />
        {props.showEventDetail && !props.playerMode && (
          <FilterField label={t("ui.tournament.round", "Runde")}>
            <SelectControl
              value={props.round}
              onChange={props.onRoundChange}
              disabled={props.roundsLoading}
              ariaLabel={t("ui.tournament.round", "Runde")}
              className="h-9 min-w-[200px] max-w-[min(28rem,90vw)] text-small"
            >
              <option value="">{t("ui.tournament.all_latest", "Gesamt")}</option>
              {props.rounds.map((r) => (
                <option
                  key={String(r.round_number)}
                  value={String(r.round_number)}
                  title={
                    formatTournamentRoundOptionLabel(r, props.rounds, t) !== String(r.round_number)
                      ? formatTournamentRoundOptionLabel(r, props.rounds, t)
                      : undefined
                  }
                >
                  {formatTournamentRoundOptionLabel(r, props.rounds, t)}
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

function FilterBarMobile(props: TournamentFilterBarProps & FormatTriggerProps) {
  const { t } = props;
  const { openMobileNav } = useMobileNav();
  const [sheetOpen, setSheetOpen] = useState(false);
  const hasTournament = props.showEventDetail;
  const hasDrillDown = props.playerMode
    ? !!props.player
    : props.showEventDetail
      ? !!(props.round || props.player)
      : !!props.player;

  const playerEntries = usePlayerEntries(props.players);
  const playerSearchDisabled = props.playersLoading;
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
        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          <CompactSeasonTournamentFields {...props} formatTrigger={props.formatTrigger} />
          {moreFiltersButton}
        </div>
      </div>

      <div className="sticky top-0 z-10 -mx-4 border-b border-border bg-background/85 px-4 py-3 backdrop-blur max-lg:landscape:hidden lg:hidden">
        <div className="grid grid-cols-2 gap-3">
          <SeasonTournamentFields
            {...props}
            selectClassName="h-11 w-full min-w-0 text-[15px]"
            tournamentInfoExtra={props.showEventDetail ? props.formatTrigger : null}
          />
        </div>

        <div className="mt-3">
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

        {hasTournament && (
          <div className="mt-3 space-y-2">
            {hasDrillDown && props.round && (
              <p className="text-small text-muted leading-snug">{summary}</p>
            )}
            <button
              type="button"
              onClick={() => setSheetOpen(true)}
              className="flex h-11 w-full items-center justify-between gap-2 rounded-sm border border-border bg-surface px-3 text-[15px] font-medium text-foreground hover:border-border-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              <span>{t("ui.tournament.round", "Runde")}</span>
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
        title={
          props.showEventDetail
            ? t("ui.tournament.round", "Runde")
            : t("more_filters", "Auswahl anpassen")
        }
        closeLabel={t("done", "Fertig")}
      >
        <div className="space-y-4">
          {props.showEventDetail && !props.playerMode ? (
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
                    title={
                      formatTournamentRoundOptionLabel(r, props.rounds, t) !== String(r.round_number)
                        ? formatTournamentRoundOptionLabel(r, props.rounds, t)
                        : undefined
                    }
                  >
                    {formatTournamentRoundOptionLabel(r, props.rounds, t)}
                  </option>
                ))}
              </SelectControl>
            </FilterField>
          ) : (
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
          )}
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
    | "showEventDetail"
    | "t"
  > & { formatTrigger?: React.ReactNode },
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
          {props.showEventDetail && props.formatTrigger ? (
        <span className="flex shrink-0 items-center">{props.formatTrigger}</span>
      ) : null}
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
  tournamentInfoExtra,
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
> & { selectClassName: string; tournamentInfoExtra?: React.ReactNode }) {
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
      <FilterField
        label={t("ui.tournament.tournament", "Turnier")}
        labelExtra={tournamentInfoExtra}
      >
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

/** Visible label for the Runde &lt;select&gt;; prefers CSV ``round_name``, disambiguates duplicate names with ``(#n)``. */
export function formatTournamentRoundOptionLabel(
  r: TournamentRound,
  allRounds: TournamentRound[],
  t: (key: string, fallback?: string) => string,
): string {
  const n = String(r.round_number ?? "");
  const rawName = r.round_name != null ? String(r.round_name).trim() : "";
  if (!rawName) {
    return `${t("ui.tournament.round", "Runde")} ${n}`;
  }
  const dup = allRounds.filter((x) => String(x.round_name ?? "").trim() === rawName).length;
  return dup > 1 ? `${rawName} (#${n})` : rawName;
}

function roundLabel(
  round: string,
  rounds: TournamentRound[],
  t: TournamentFilterBarProps["t"],
): string {
  const found = rounds.find((r) => String(r.round_number) === round);
  if (found) return formatTournamentRoundOptionLabel(found, rounds, t);
  return `${t("ui.tournament.round", "Runde")} ${round}`;
}

function formatHandicapPinsLine(b: HandicapFormatBand, t: TournamentFilterBarProps["t"]): string {
  if (b.kind === "uniform") {
    return t("ui.tournament.format_handicap_pins_uniform", "{n} Pins pro Spiel").replace(
      "{n}",
      String(b.value),
    );
  }
  return t(
    "ui.tournament.format_handicap_pins_range",
    "{min}–{max} Pins pro Spiel (Ø {mean})",
  )
    .replace("{min}", String(b.min))
    .replace("{max}", String(b.max))
    .replace("{mean}", String(b.mean));
}

function formatHandicapMetricLine(
  b: HandicapFormatBand,
  t: TournamentFilterBarProps["t"],
  uniformKey: string,
  uniformFallback: string,
  rangeKey: string,
  rangeFallback: string,
): string {
  if (b.kind === "uniform") {
    return t(uniformKey, uniformFallback).replace("{v}", String(b.value));
  }
  return t(rangeKey, rangeFallback)
    .replace("{min}", String(b.min))
    .replace("{max}", String(b.max))
    .replace("{mean}", String(b.mean));
}

function usePlayerEntries(players: string[]) {
  return useMemo(() => players.map((name) => ({ id: name, name })), [players]);
}

function FormatInfoIconButton({
  onClick,
  disabled,
  ariaLabel,
}: {
  onClick: () => void;
  disabled?: boolean;
  ariaLabel: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      title={ariaLabel}
      className="inline-flex size-7 shrink-0 items-center justify-center rounded-sm border border-border bg-surface text-muted hover:border-border-strong hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-40"
    >
      <Info size={16} strokeWidth={1.75} aria-hidden />
    </button>
  );
}

function TournamentFormatModal({
  open,
  onClose,
  t,
  query,
}: {
  open: boolean;
  onClose: () => void;
  t: TournamentFilterBarProps["t"];
  query: UseQueryResult<TournamentFormatInfo, Error>;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const d = query.data;
  const handicapFmt = d?.handicap ?? EMPTY_TOURNAMENT_HANDICAP_FORMAT;
  const err = query.isError
    ? query.error instanceof Error
      ? query.error.message
      : t("error_generic", "Fehler beim Laden")
    : null;

  return (
    <div className="fixed inset-0 z-[100] flex items-end justify-center p-0 sm:items-center sm:p-4">
      <button
        type="button"
        aria-label={t("close", "Schließen")}
        className="absolute inset-0 bg-black/40 backdrop-blur-[2px]"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="tournament-format-title"
        className="relative z-[101] flex max-h-[85vh] w-full max-w-lg flex-col rounded-t-sm border border-border bg-surface shadow-lg sm:rounded-sm"
      >
        <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <h2 id="tournament-format-title" className="text-h3 pr-8">
            {t("ui.tournament.format_title", "Turnierformat")}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("close", "Schließen")}
            className="absolute right-3 top-3 rounded-sm p-1 text-muted hover:bg-surface-subtle hover:text-foreground"
          >
            <X size={18} strokeWidth={1.75} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 text-small">
          {query.isPending && (
            <p className="text-muted">{t("ui.common.loading", "Laden…")}</p>
          )}
          {err && <p className="text-danger-fg">{err}</p>}
          {d && (
            <div className="space-y-5">
              <section>
                <h3 className="text-label uppercase text-muted">
                  {t("ui.tournament.format_rounds_heading", "Runden (Daten)")}
                </h3>
                <p className="mt-1 text-muted">
                  {t("ui.tournament.format_round_count", "{n} Phasen").replace(
                    "{n}",
                    String(d.round_count),
                  )}
                </p>
                {d.rounds.length > 0 ? (
                  <ul className="mt-2 list-inside list-disc space-y-1 text-body">
                    {d.rounds.map((row) => {
                      const label =
                        row.round_name?.trim() ||
                        `${t("ui.tournament.round", "Runde")} ${row.round_number}`;
                      const tag = row.is_ko_finale_cluster
                        ? t("ui.tournament.format_ko_tag", "KO")
                        : null;
                      return (
                        <li key={row.round_number}>
                          <span className="font-mono text-muted">{row.round_number}.</span>{" "}
                          {label}
                          {tag ? (
                            <span className="ml-1.5 rounded-xs border border-border px-1 py-0.5 text-label text-muted">
                              {tag}
                            </span>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <p className="mt-1 text-muted">
                    {t("ui.tournament.format_no_rounds", "Keine Runden in den Rohdaten.")}
                  </p>
                )}
              </section>

              <section>
                <h3 className="text-label uppercase text-muted">
                  {t("ui.tournament.format_handicap_heading", "Handicap (Ergebnisdaten)")}
                </h3>
                {handicapFmt.used ? (
                  <p className="mt-1 text-body text-muted">
                    {t(
                      "ui.tournament.format_handicap_used_hint",
                      "Scratch- und Net-Ranglisten nutzen die Handicap-Spalten aus den Importdaten.",
                    )}
                  </p>
                ) : (
                  <p className="mt-1 text-body text-muted">
                    {t(
                      "ui.tournament.format_handicap_not_used_hint",
                      "Keine verwertbaren Handicap-/A-Priori-Werte (nur Scratch relevant oder Spalten fehlen).",
                    )}
                  </p>
                )}
                <ul className="mt-2 space-y-1.5 text-body">
                  {handicapFmt.columns.handicap ? (
                    <li>
                      <span className="text-muted">
                        {t("ui.tournament.handicap_col_short", "Hcp")}:{" "}
                      </span>
                      {handicapFmt.pins != null
                        ? formatHandicapPinsLine(handicapFmt.pins, t)
                        : t(
                            "ui.tournament.format_handicap_column_empty",
                            "Spalte vorhanden, keine Pins-Werte.",
                          )}
                    </li>
                  ) : (
                    <li className="text-muted">
                      {t(
                        "ui.tournament.format_handicap_no_pins_col",
                        "Keine Spalte „Handicap“ in den Daten.",
                      )}
                    </li>
                  )}
                  {handicapFmt.columns.apriori_average ? (
                    <li>
                      <span className="text-muted">
                        {t("ui.tournament.apriori_avg_label", "A-Priori-Ø")}:{" "}
                      </span>
                      {handicapFmt.a_priori_average != null
                        ? formatHandicapMetricLine(
                            handicapFmt.a_priori_average,
                            t,
                            "ui.tournament.format_handicap_apriori_uniform",
                            "{v}",
                            "ui.tournament.format_handicap_apriori_range",
                            "{min}–{max} (Ø {mean})",
                          )
                        : t(
                            "ui.tournament.format_handicap_value_empty",
                            "Spalte vorhanden, keine numerischen Werte.",
                          )}
                    </li>
                  ) : null}
                  {handicapFmt.columns.handicap_reference ? (
                    <li>
                      <span className="text-muted">
                        {t("ui.tournament.handicap_ref_label", "Referenz")}:{" "}
                      </span>
                      {handicapFmt.handicap_reference != null
                        ? formatHandicapMetricLine(
                            handicapFmt.handicap_reference,
                            t,
                            "ui.tournament.format_handicap_reference_uniform",
                            "{v}",
                            "ui.tournament.format_handicap_reference_range",
                            "{min}–{max} (Ø {mean})",
                          )
                        : t(
                            "ui.tournament.format_handicap_value_empty",
                            "Spalte vorhanden, keine numerischen Werte.",
                          )}
                    </li>
                  ) : null}
                </ul>
              </section>

              <section>
                <h3 className="text-label uppercase text-muted">
                  {t("ui.tournament.format_ko_heading", "KO & Schnitt")}
                </h3>
                <ul className="mt-2 space-y-1.5 text-body">
                  {d.ko_finale_series_label_de ? (
                    <li>
                      <span className="text-muted">
                        {t("ui.tournament.format_ko_finale_mode", "KO-Finale")}:{" "}
                      </span>
                      {d.ko_finale_series_label_de}
                    </li>
                  ) : null}
                  {d.ko_bracket_format === "seeded_elim_stepladder" ? (
                    <li className="text-small text-muted">
                      {t(
                        "ui.tournament.format_stepladder_detail",
                        "Alle Entscheidungen inkl. Handicap. Seeds 4–6: Eliminierung Spiel-für-Spiel (niedrigster raus) · Seeds 2/3 + Elim-Sieger: Stepladder 1 Spiel · #1 vs Stepladder-Sieger: Best-of-3",
                      )}
                    </li>
                  ) : null}
                  {d.ko_finale_round_number_in_data != null ? (
                    <li>
                      <span className="text-muted">
                        {t("ui.tournament.format_ko_round_index", "KO-Runde (Nr.)")}:{" "}
                      </span>
                      {d.ko_finale_round_number_in_data}
                    </li>
                  ) : null}
                  {d.qualifying_cut_span ? (
                    <li>
                      {t(
                        "ui.tournament.format_cut_span",
                        "Cut / Qualifikation: Top {rank} nach Runde {from} bis {through}",
                      )
                        .replace("{rank}", String(d.qualifying_cut_span.rank))
                        .replace("{from}", String(d.qualifying_cut_span.first_round))
                        .replace("{through}", String(d.qualifying_cut_span.through_round))}
                    </li>
                  ) : null}
                  {d.qualifying_cut_pair && !d.qualifying_cut_span ? (
                    <li>
                      {t("ui.tournament.format_cut_pair", "Cut-Platzierung: Top {rank} (Runde {r})")
                        .replace("{rank}", String(d.qualifying_cut_pair.rank))
                        .replace("{r}", String(d.qualifying_cut_pair.round))}
                    </li>
                  ) : null}
                  {d.qualifying_stages?.length ? (
                    <li className="mt-2">
                      <span className="text-muted">
                        {t("ui.tournament.format_stage_cuts", "Stufen-Cuts")}:
                      </span>
                      <ul className="mt-1 list-inside list-disc pl-1">
                        {d.qualifying_stages.map((stage) => (
                          <li key={stage.round_number}>
                            {stage.name}
                            {stage.cut && stage.cut !== "n/a"
                              ? ` — Top ${stage.cut}`
                              : ""}
                          </li>
                        ))}
                      </ul>
                    </li>
                  ) : null}
                </ul>
              </section>

              {Object.keys(d.config).length > 0 ? (
                <section>
                  <h3 className="text-label uppercase text-muted">
                    {t("ui.tournament.format_config_heading", "Konfiguration (Datei)")}
                  </h3>
                  <dl className="mt-2 grid gap-x-3 gap-y-1 text-body sm:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
                    {Object.entries(d.config).map(([k, v]) => (
                      <div key={k} className="contents">
                        <dt className="font-mono text-muted break-all">{k}</dt>
                        <dd className="break-words">
                          {Array.isArray(v) ? v.join(", ") : String(v)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </section>
              ) : null}

              {d.config_note ? (
                <section>
                  <h3 className="text-label uppercase text-muted">
                    {t("ui.tournament.format_note_heading", "Hinweis")}
                  </h3>
                  <p className="mt-1 whitespace-pre-wrap text-body text-muted">{d.config_note}</p>
                </section>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function FilterField({
  label,
  labelExtra,
  children,
}: {
  label: string;
  labelExtra?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="flex min-h-[1.25rem] flex-wrap items-center gap-1.5">
        <span className="text-label uppercase text-muted">{label}</span>
        {labelExtra}
      </span>
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
