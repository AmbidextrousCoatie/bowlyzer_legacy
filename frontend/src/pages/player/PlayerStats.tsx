import { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { PlayerSearch } from "../../components/PlayerSearch";
import {
  type PlayerSearchEntry,
  usePlayerLifetimeStats,
  usePlayerSearch,
  usePlayerSeasons,
} from "../../hooks/usePlayer";
import { useTranslations } from "../../hooks/useTranslations";
import { buildPlayerClubHistory } from "../../lib/playerClubHistory";
import { ClubAffiliationHistory } from "./blocks/ClubHistory";
import { LifetimeStats } from "./blocks/LifetimeStats";
import { SeasonStats } from "./blocks/SeasonStats";
import { TrendChart } from "./blocks/TrendChart";

export function PlayerStats() {
  const { t } = useTranslations();
  const [searchParams, setSearchParams] = useSearchParams();

  const playerName = searchParams.get("player_name") ?? searchParams.get("player") ?? "";
  const playerId = searchParams.get("player_id") ?? "";
  const season = searchParams.get("season") ?? "all";

  const playersQuery = usePlayerSearch();
  const seasonsQuery = usePlayerSeasons(playerName, playerId);
  const statsQuery = usePlayerLifetimeStats(playerName, playerId, season);

  // If the URL points at a player not present in the current data source,
  // surface a soft warning rather than running queries that 400. The hook is
  // still gated on `enabled`, so no requests fire while this resolves.
  const players = playersQuery.data ?? [];
  const knownPlayer = useMemo(() => {
    if (!playerName && !playerId) return null;
    return (
      players.find(
        (p) =>
          (playerId && p.id === playerId) ||
          (playerName && p.name.toLowerCase() === playerName.toLowerCase()),
      ) ?? null
    );
  }, [players, playerName, playerId]);

  // If the URL has player_name but the actual lookup resolved a canonical
  // entry with a slightly different spelling, normalize it once players load.
  useEffect(() => {
    if (!playersQuery.isSuccess || !knownPlayer || !playerName) return;
    if (knownPlayer.name !== playerName || (knownPlayer.id && knownPlayer.id !== playerId)) {
      const next = new URLSearchParams(searchParams);
      next.set("player_name", knownPlayer.name);
      if (knownPlayer.id) next.set("player_id", knownPlayer.id);
      setSearchParams(next, { replace: true });
    }
  }, [playersQuery.isSuccess, knownPlayer, playerName, playerId, searchParams, setSearchParams]);

  // Keep season scope valid: if the player doesn't have data in `season`,
  // fall back to "all".
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
      next.delete("season");
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
    else next.set("season", value);
    setSearchParams(next, { replace: false });
  }

  const stats = statsQuery.data;
  const lifetime = stats?.lifetime ?? null;
  const seasonRows = stats?.seasons ?? [];
  const seasons = seasonsQuery.data ?? [];

  const { currentClub, historyRows } = useMemo(
    () => buildPlayerClubHistory(stats?.seasons ?? []),
    [stats?.seasons],
  );

  const hasSelection = !!(playerName || playerId);
  const hasResolvedPlayers = playersQuery.isSuccess;
  const playerNotFound = hasSelection && hasResolvedPlayers && !knownPlayer;

  return (
    <div className="mx-auto max-w-[1280px] px-8 pt-12 pb-24">
      <header className="mb-8">
        <p className="text-label uppercase text-muted mb-2">
          {t("ui.player.title", "Bowl-A-Lyzer")}
        </p>
        <h1 className="text-h1">
          {t("ui.player.stats_headline", "Spielerstatistiken")}
          {playerName ? (
            <>
              {" "}
              · <span className="text-muted font-normal">{playerName}</span>
              {currentClub ? (
                <>
                  {" "}
                  · <span className="text-muted font-normal">{currentClub}</span>
                </>
              ) : null}
            </>
          ) : null}
        </h1>
      </header>

      <FilterRail
        playerName={playerName}
        players={players}
        playersLoading={playersQuery.isPending}
        season={season}
        seasons={seasons}
        seasonsLoading={seasonsQuery.isPending && hasSelection}
        onPlayerSelect={selectPlayer}
        onSeasonSelect={selectSeason}
        t={t}
      />

      <div className="mt-10 space-y-12">
        {!hasSelection && (
          <section className="rounded-sm border border-dashed border-border p-8 text-center">
            <p className="text-body text-muted">
              {t("ui.player.select_player", "Spieler auswählen")} —{" "}
              {t("ui.player.type_name_placeholder", "Namen eintippen oder aus der Liste wählen.")}
            </p>
          </section>
        )}

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

        {hasSelection && !playerNotFound && (
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
                    "ui.player.no_data_for_player_desc",
                    "Für diesen Spieler liegen keine Daten in der aktuellen Datenquelle vor.",
                  )}
                </section>
              )}

            {statsQuery.isSuccess && stats && (
              <>
                <LifetimeStats
                  stats={lifetime}
                  playerId={playerId || knownPlayer?.id || undefined}
                  t={t}
                />
                <SeasonStats seasons={seasonRows} selectedPlayerName={playerName} t={t} />
                <TrendChart seasons={seasonRows} lifetime={lifetime} t={t} />
                <ClubAffiliationHistory rows={historyRows} t={t} />
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
  const showSeasons = !!props.playerName && (props.seasons.length > 0 || props.seasonsLoading);

  return (
    <div className="sticky top-0 z-10 -mx-8 border-b border-border bg-background/85 px-8 py-3 backdrop-blur">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <FilterField label={t("ui.player.select_player", "Spieler")}>
          <PlayerSearch
            value={props.playerName}
            players={props.players}
            isLoading={props.playersLoading}
            placeholder={t("ui.player.type_name_placeholder", "Name eingeben…")}
            ariaLabel={t("ui.player.select_player", "Spieler auswählen")}
            clearAriaLabel={t("ui.player.clear_player", "Spieler-Auswahl löschen")}
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
