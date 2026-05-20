import { useEffect, useMemo, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { ClubSearch } from "../../components/ClubSearch";
import { useClubMatrix } from "../../hooks/useLeague";
import { useTeamSeasons, useTeams } from "../../hooks/useTeam";
import { useTranslations } from "../../hooks/useTranslations";
import {
  getClubTeamColor,
  normalizeUnicodeLabel,
  splitClubAndTeamNumber,
  teamDisplayLabel,
  teamsForClub,
} from "../../lib/teamUtils";
import { ClubOverview } from "./blocks/ClubOverview";
import { TeamDetail } from "./blocks/TeamDetail";

export function TeamStats() {
  const { t } = useTranslations();
  const [searchParams, setSearchParams] = useSearchParams();

  const clubParam = searchParams.get("club") ?? "";
  const teamParam = searchParams.get("team") ?? "";
  const season = searchParams.get("season") ?? "all";

  const club = useMemo(() => {
    const raw = clubParam
      ? clubParam
      : teamParam
        ? splitClubAndTeamNumber(teamParam).club
        : "";
    return normalizeUnicodeLabel(raw);
  }, [clubParam, teamParam]);

  const teamsQuery = useTeams();
  const clubsQuery = useClubMatrix(null, false);
  const clubMatrixQuery = useClubMatrix(club || null, false);
  const teamSeasonsQuery = useTeamSeasons(teamParam || null);

  const allTeams = teamsQuery.data ?? [];
  const clubs = clubsQuery.data?.clubs ?? clubMatrixQuery.data?.clubs ?? [];

  const clubTeams = useMemo(
    () => (club ? teamsForClub(allTeams, club) : []),
    [allTeams, club],
  );

  const team = useMemo(() => {
    if (!teamParam) return "";
    const nt = normalizeUnicodeLabel(teamParam);
    const fromList = clubTeams.find((n) => normalizeUnicodeLabel(n) === nt);
    if (fromList) return fromList;
    const teamClub = normalizeUnicodeLabel(splitClubAndTeamNumber(teamParam).club);
    if (teamClub === club) return normalizeUnicodeLabel(teamParam);
    return "";
  }, [teamParam, clubTeams, club]);

  useEffect(() => {
    if (!teamsQuery.isSuccess || !club) return;
    const next = new URLSearchParams(searchParams);
    let changed = false;
    if (!clubParam && club) {
      next.set("club", club);
      changed = true;
    }
    if (teamParam && team && team !== teamParam) {
      next.set("team", team);
      changed = true;
    }
    if (changed) setSearchParams(next, { replace: true });
  }, [teamsQuery.isSuccess, clubParam, club, teamParam, team, searchParams, setSearchParams]);

  useEffect(() => {
    if (!teamSeasonsQuery.isSuccess || !team) return;
    if (season === "all") return;
    const seasons = teamSeasonsQuery.data ?? [];
    if (!seasons.includes(season)) {
      const next = new URLSearchParams(searchParams);
      next.delete("season");
      setSearchParams(next, { replace: true });
    }
  }, [teamSeasonsQuery.isSuccess, teamSeasonsQuery.data, season, team, searchParams, setSearchParams]);

  function selectClub(value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set("club", value);
    else next.delete("club");
    next.delete("team");
    next.delete("season");
    setSearchParams(next, { replace: false });
  }

  function selectTeam(value: string) {
    const next = new URLSearchParams(searchParams);
    if (!club) return;
    if (value) next.set("team", value);
    else next.delete("team");
    next.delete("season");
    setSearchParams(next, { replace: false });
  }

  function selectSeason(value: string) {
    const next = new URLSearchParams(searchParams);
    if (!value || value === "all") next.delete("season");
    else next.set("season", value);
    setSearchParams(next, { replace: false });
  }

  const matrix = clubMatrixQuery.data?.matrix;
  const matrixRows = matrix && matrix.club === club ? matrix.rows : [];
  const matrixSeasons = matrix && matrix.club === club ? matrix.seasons : [];

  const showClubOverview = !!club && !team;
  const showTeamDetail = !!club && !!team;

  return (
    <div className="mx-auto max-w-[1280px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <header className="mb-6 lg:mb-8">
        <p className="text-label uppercase text-muted mb-2">
          {t("ui.team.eyebrow", "Akteure")}
        </p>
        <h1 className="text-h1">
          {t("ui.team.page_title", "Club")}
          {club ? (
            <>
              {" "}
              · <span className="font-normal text-muted">{club}</span>
            </>
          ) : null}
        </h1>
        <p className="text-body text-muted mt-2 max-w-[72ch]">
          {t(
            "ui.team.page_desc",
            "Club-Übersicht mit allen Mannschaften — Detailanalyse pro Team wie in der bisherigen Mannschaftsansicht.",
          )}
        </p>
      </header>

      <div className="sticky top-0 z-10 -mx-4 border-b border-border bg-background/85 px-4 py-3 backdrop-blur lg:-mx-8 lg:px-8">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
          <FilterField label={t("ui.team.club", "Club")}>
            <ClubSearch
              value={club}
              clubs={clubs}
              isLoading={clubsQuery.isPending}
              placeholder={t("ui.team.select_club", "Club eingeben oder wählen…")}
              ariaLabel={t("ui.team.select_club", "Club wählen")}
              clearAriaLabel={t("ui.team.clear_club", "Club-Auswahl löschen")}
              onSelect={(c) => selectClub(c ?? "")}
            />
          </FilterField>

          {club && clubTeams.length > 0 && (
            <FilterField label={t("team", "Mannschaft")}>
              <select
                className="h-9 min-w-[min(100%,280px)] rounded-sm border border-border bg-surface-subtle px-2.5 text-small"
                value={team}
                onChange={(e) => selectTeam(e.target.value)}
                style={
                  team
                    ? { borderLeftWidth: 4, borderLeftColor: getClubTeamColor(team) }
                    : undefined
                }
              >
                <option value="">{t("ui.team.club_overview", "Club-Übersicht")}</option>
                {clubTeams.map((name) => (
                  <option key={name} value={name}>
                    {teamDisplayLabel(name)} — {name}
                  </option>
                ))}
              </select>
            </FilterField>
          )}
        </div>
      </div>

      <div className="mt-8 space-y-8">
        {!club && (
          <section className="rounded-sm border border-dashed border-border p-8 text-center">
            <p className="text-body text-muted">
              {t("ui.team.select_club_prompt", "Wähle einen Club, um seine Mannschaften zu sehen.")}
            </p>
          </section>
        )}

        {club && clubTeams.length === 0 && teamsQuery.isSuccess && (
          <section className="rounded-sm border border-warning/40 bg-surface p-6 text-small">
            {t(
              "ui.team.no_teams_for_club",
              "Für diesen Club wurden keine Mannschaften in der Datenquelle gefunden.",
            )}
          </section>
        )}

        {showClubOverview && clubTeams.length > 0 && (
          <ClubOverview
            club={club}
            teams={clubTeams}
            matrixRows={matrixRows}
            seasons={matrixSeasons}
            leagueLongNames={clubMatrixQuery.data?.league_long_names ?? {}}
            t={t}
          />
        )}

        {showTeamDetail && (
          <TeamDetail
            club={club}
            teamName={team}
            season={season}
            seasons={teamSeasonsQuery.data ?? []}
            onSeasonChange={selectSeason}
            t={t}
          />
        )}
      </div>
    </div>
  );
}

function FilterField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-label text-muted">{label}</span>
      {children}
    </label>
  );
}
