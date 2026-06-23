import { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { PlayerSearch } from "../../components/PlayerSearch";
import { seasonForUrlQuery } from "../../lib/api";
import {
  type PlayerSearchEntry,
  isAllPlayersScope,
  usePlayerLifetimeStats,
  usePlayerSearch,
  usePlayerSeasons,
} from "../../hooks/usePlayer";
import { useTranslations } from "../../hooks/useTranslations";
import { buildPlayerClubHistory } from "../../lib/playerClubHistory";
import { formatPlayerSearchLabel, resolvePlayerSearchEntry } from "../../lib/playerSearchLabel";
import { LifetimeStats } from "./blocks/LifetimeStats";
import { CompetitionBreakdownCharts } from "./blocks/CompetitionBreakdownCharts";
import { PlayerHighlights } from "./blocks/PlayerHighlights";
import { TrendChart } from "./blocks/TrendChart";

export function PlayerStats() {
  const { t, formatCompetition } = useTranslations();
  const [searchParams, setSearchParams] = useSearchParams();

  const playerName = searchParams.get("player_name") ?? searchParams.get("player") ?? "";
  const playerId = searchParams.get("player_id") ?? "";
  const season = searchParams.get("season") ?? "all";

  const playersQuery = usePlayerSearch();
  const seasonsQuery = usePlayerSeasons(playerName, playerId);
  const statsQuery = usePlayerLifetimeStats(playerName, playerId, season);

  const players = playersQuery.data ?? [];
  const knownPlayer = useMemo(
    () =>
      playerName || playerId
        ? resolvePlayerSearchEntry(players, { name: playerName, id: playerId })
        : null,
    [players, playerName, playerId],
  );

  useEffect(() => {
    if (!playersQuery.isSuccess || !knownPlayer) return;
    const next = new URLSearchParams(searchParams);
    let changed = false;
    if (knownPlayer.name && knownPlayer.name !== playerName) {
      next.set("player_name", knownPlayer.name);
      changed = true;
    }
    if (knownPlayer.id && !playerId) {
      next.set("player_id", knownPlayer.id);
      changed = true;
    }
    if (changed) setSearchParams(next, { replace: true });
  }, [playersQuery.isSuccess, knownPlayer, playerName, playerId, searchParams, setSearchParams]);

  useEffect(() => {
    if (!seasonsQuery.isSuccess) return;
    if (season === "all") return;
    const seasons = seasonsQuery.data ?? [];
    if (!seasons.includes(season)) {
      const next = new URLSearchParams(searchParams);
      next.delete("season");
      setSearchParams(next, { replace: true });
    }
  }, [seasonsQuery.isSuccess, seasonsQuery.data, season, searchParams, setSearchParams]);

  function selectPlayer(entry: PlayerSearchEntry | null) {
    const next = new URLSearchParams(searchParams);
    if (!entry) {
      next.delete("player_name");
      next.delete("player");
      next.delete("player_id");
      setSearchParams(next, { replace: false });
      return;
    }
    next.set("player_name", entry.name);
    if (entry.id) next.set("player_id", entry.id);
    else next.delete("player_id");
    next.delete("player");
    next.delete("season");
    setSearchParams(next, { replace: false });
  }

  function selectSeason(value: string) {
    const next = new URLSearchParams(searchParams);
    if (!value || value === "all") next.delete("season");
    else next.set("season", seasonForUrlQuery(value));
    setSearchParams(next, { replace: false });
  }

  const hasPlayerSelection = !!(playerName || playerId);
  const playerSearchValue =
    knownPlayer && (knownPlayer.id || playerId)
      ? formatPlayerSearchLabel({
          name: knownPlayer.name,
          id: knownPlayer.id || playerId,
        })
      : playerName;

  const stats = statsQuery.data;
  const allPlayersScope = isAllPlayersScope(stats);
  const lifetime = stats?.lifetime ?? null;
  const seasonRows = stats?.seasons ?? [];
  const periodRows = stats?.periods ?? [];
  const seasons = seasonsQuery.data ?? [];

  const { currentClub } = useMemo(
    () => buildPlayerClubHistory(hasPlayerSelection ? (stats?.seasons ?? []) : []),
    [hasPlayerSelection, stats?.seasons],
  );

  const hasResolvedPlayers = playersQuery.isSuccess;
  const playerNotFound = hasPlayerSelection && hasResolvedPlayers && !knownPlayer;

  const headlineSuffix = hasPlayerSelection
    ? playerName
    : t("ui.player.all_players_scope", "Alle Spieler");

  return (
    <div className="mx-auto max-w-[1280px] px-8 pt-12 pb-24">
      <header className="mb-8">
        <p className="text-label uppercase text-muted mb-2">
          {t("ui.player.title", "Bowl-A-Lyzer")}
        </p>
        <h1 className="text-h1">
          {t("ui.player.stats_headline", "Spielerstatistiken")}
          {" "}
          · <span className="text-muted font-normal">{headlineSuffix}</span>
          {hasPlayerSelection && currentClub ? (
            <>
              {" "}
              · <span className="text-muted font-normal">{currentClub}</span>
            </>
          ) : null}
        </h1>
      </header>

      <FilterRail
        playerName={playerSearchValue}
        players={players}
        playersLoading={playersQuery.isPending}
        season={season}
        seasons={seasons}
        seasonsLoading={seasonsQuery.isPending}
        onPlayerSelect={selectPlayer}
        onSeasonSelect={selectSeason}
        t={t}
      />

      <div className="mt-10 space-y-12">
        {playerNotFound && (
          <section className="rounded-sm border border-warning/40 bg-surface p-6 text-small text-foreground">
            <strong>{t("ui.player.player_not_found", "Spieler nicht gefunden")}:</strong>{" "}
            {`"${playerName}" `}
            {t(
              "ui.player.player_not_found_desc",
              "ist in der aktuellen Datenquelle nicht vorhanden.",
            )}
          </section>
        )}

        {!playerNotFound && (
          <>
            {statsQuery.isError && (
              <section className="rounded-sm border border-danger-fg/40 bg-surface p-6 text-small text-danger-fg">
                {statsQuery.error instanceof Error
                  ? statsQuery.error.message
                  : t("error_generic", "Fehler beim Laden")}
              </section>
            )}

            {statsQuery.isPending && <LoadingSection t={t} />}

            {statsQuery.isSuccess &&
              (!stats || (!stats.lifetime && (!stats.seasons || stats.seasons.length === 0))) && (
                <section className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
                  {t(
                    "ui.player.no_data_desc",
                    "Für die aktuelle Auswahl liegen keine Daten in der Datenquelle vor.",
                  )}
                </section>
              )}

            {statsQuery.isSuccess && stats && stats.lifetime && (
              <>
                <LifetimeStats
                  stats={lifetime}
                  playerId={hasPlayerSelection ? playerId || knownPlayer?.id || undefined : undefined}
                  allPlayersScope={allPlayersScope}
                  t={t}
                />
                <CompetitionBreakdownCharts
                  seasons={seasonRows}
                  t={t}
                  formatCompetition={formatCompetition}
                />
                <PlayerHighlights
                  scope={allPlayersScope ? "all" : "player"}
                  seasons={seasonRows}
                  periods={periodRows}
                  playerCompetitions={stats.player_competitions ?? []}
                  playerSeasonTotals={stats.player_season_totals ?? []}
                  selectedPlayerName={playerName}
                  t={t}
                />
                <TrendChart seasons={seasonRows} lifetime={lifetime} t={t} />
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

type FilterRailProps = {
  playerName: string;
  players: PlayerSearchEntry[];
  playersLoading: boolean;
  season: string;
  seasons: string[];
  seasonsLoading: boolean;
  onPlayerSelect: (entry: PlayerSearchEntry | null) => void;
  onSeasonSelect: (value: string) => void;
  t: (key: string, fallback?: string) => string;
};

function FilterRail(props: FilterRailProps) {
  const { t } = props;
  const showSeasons = props.seasons.length > 0 || props.seasonsLoading;

  return (
    <div className="sticky top-0 z-10 -mx-8 border-b border-border bg-background/85 px-8 py-3 backdrop-blur">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <FilterField label={t("ui.player.select_player", "Spieler")}>
          <PlayerSearch
            value={props.playerName}
            players={props.players}
            isLoading={props.playersLoading}
            placeholder={t("ui.player.type_name_placeholder", "Name oder Spieler-ID…")}
            ariaLabel={t("ui.player.select_player", "Spieler auswählen")}
            clearAriaLabel={t("ui.player.clear_player", "Alle Spieler anzeigen")}
            onSelect={props.onPlayerSelect}
          />
        </FilterField>

        {showSeasons && (
          <FilterField label={t("ui.player.season_scope", "Saison-Auswahl")}>
            <div className="flex flex-wrap gap-1">
              <SeasonChip
                active={props.season === "all"}
                disabled={props.seasonsLoading}
                onClick={() => props.onSeasonSelect("all")}
              >
                {t("ui.player.all_time", "Karriere")}
              </SeasonChip>
              {props.seasons.map((s) => (
                <SeasonChip
                  key={s}
                  active={props.season === s}
                  disabled={props.seasonsLoading}
                  onClick={() => props.onSeasonSelect(s)}
                >
                  {s}
                </SeasonChip>
              ))}
            </div>
          </FilterField>
        )}
      </div>
    </div>
  );
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-label uppercase text-muted">{label}</span>
      {children}
    </label>
  );
}

function SeasonChip({
  active,
  disabled,
  onClick,
  children,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={
        "h-9 rounded-sm border px-3 text-small font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60 " +
        (active
          ? "border-accent bg-accent text-accent-foreground hover:bg-accent-hover"
          : "border-border bg-surface text-foreground hover:border-border-strong")
      }
    >
      {children}
    </button>
  );
}

function LoadingSection({ t }: { t: (key: string, fallback?: string) => string }) {
  return (
    <section className="space-y-4" aria-label={t("status.loading", "Lade Daten…")}>
      <div className="h-3 w-24 rounded-xs bg-surface-subtle" />
      <div className="h-6 w-64 rounded-xs bg-surface-subtle" />
      <div className="h-48 rounded-sm border border-border bg-surface-subtle" />
    </section>
  );
}
