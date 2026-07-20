import { useEffect, useMemo, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { ClubSearch } from "../../components/ClubSearch";
import { seasonForUrlQuery } from "../../lib/api";
import { useClubMatrix, type ClubMatrixPayload } from "../../hooks/useLeague";
import { useMyClub } from "../../hooks/useMyClub";
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
  const { active: myClubActive, resolvedClub: myClubResolved, myClub } = useMyClub();

  const clubParam = searchParams.get("club") ?? "";
  const teamParam = searchParams.get("team") ?? "";
  const season = searchParams.get("season") ?? "all";

  const club = useMemo(() => {
    // Mein Club owns the page lens — no separate club picker.
    if (myClubActive) {
      return normalizeUnicodeLabel(myClubResolved || myClub);
    }
    const raw = clubParam ? clubParam : teamParam ? splitClubAndTeamNumber(teamParam).club : "";
    return normalizeUnicodeLabel(raw);
  }, [myClubActive, myClubResolved, myClub, clubParam, teamParam]);

  const teamsQuery = useTeams();
  /** Always load club names so URL / typed labels can resolve to canonical spellings. */
  const clubsListQuery = useClubMatrix(null, false, { enabled: !myClubActive });
  const teamSeasonsQuery = useTeamSeasons(teamParam || null);

  const resolvedClub = useMemo(() => {
    if (!club) return "";
    if (myClubActive && myClubResolved) return myClubResolved;
    const list = clubsListQuery.data?.clubs;
    if (!list?.length) return club;
    return list.find((c) => normalizeUnicodeLabel(c) === normalizeUnicodeLabel(club)) ?? club;
  }, [club, clubsListQuery.data?.clubs, myClubActive, myClubResolved]);

  const clubMatrixQuery = useClubMatrix(resolvedClub || null, false, {
    enabled: !!resolvedClub && (myClubActive || clubsListQuery.isFetched),
  });

  const allTeams = teamsQuery.data ?? [];
  const clubs = clubsListQuery.data?.clubs ?? clubMatrixQuery.data?.clubs ?? [];

  const clubTeams = useMemo(() => (club ? teamsForClub(allTeams, club) : []), [allTeams, club]);

  const team = useMemo(() => {
    if (!teamParam) return "";
    const nt = normalizeUnicodeLabel(teamParam);
    const fromList = clubTeams.find((n) => normalizeUnicodeLabel(n) === nt);
    if (fromList) return fromList;
    const teamClub = normalizeUnicodeLabel(splitClubAndTeamNumber(teamParam).club);
    if (teamClub === club) return normalizeUnicodeLabel(teamParam);
    return "";
  }, [teamParam, clubTeams, club]);

  // Keep page-local ``club=`` in sync with Mein Club (and clear foreign teams).
  useEffect(() => {
    if (!myClubActive) return;
    const clubForUrl = (myClubResolved || myClub || "").trim();
    if (!clubForUrl) return;
    const next = new URLSearchParams(searchParams);
    let changed = false;
    if (normalizeUnicodeLabel(clubParam) !== normalizeUnicodeLabel(clubForUrl)) {
      next.set("club", clubForUrl);
      changed = true;
    }
    if (teamParam) {
      const teamClub = normalizeUnicodeLabel(splitClubAndTeamNumber(teamParam).club);
      if (teamClub !== normalizeUnicodeLabel(clubForUrl)) {
        next.delete("team");
        next.delete("season");
        changed = true;
      }
    }
    if (changed) setSearchParams(next, { replace: true });
  }, [myClubActive, myClubResolved, myClub, clubParam, teamParam, searchParams, setSearchParams]);

  useEffect(() => {
    if (myClubActive) return;
    if (!teamsQuery.isSuccess || !club) return;
    const next = new URLSearchParams(searchParams);
    let changed = false;
    const clubForUrl = resolvedClub || club;
    if (!clubParam && clubForUrl) {
      next.set("club", clubForUrl);
      changed = true;
    }
    if (teamParam && team && team !== teamParam) {
      next.set("team", team);
      changed = true;
    }
    if (changed) setSearchParams(next, { replace: true });
  }, [
    myClubActive,
    teamsQuery.isSuccess,
    clubParam,
    club,
    resolvedClub,
    teamParam,
    team,
    searchParams,
    setSearchParams,
  ]);

  useEffect(() => {
    if (myClubActive) return;
    if (!clubMatrixQuery.isSuccess || !club) return;
    const canonical = (
      clubMatrixQuery.data?.selected_club ||
      clubMatrixQuery.data?.matrix.club ||
      ""
    ).trim();
    if (!canonical) return;
    if (normalizeUnicodeLabel(canonical) === normalizeUnicodeLabel(clubParam || club)) return;
    const next = new URLSearchParams(searchParams);
    next.set("club", canonical);
    setSearchParams(next, { replace: true });
  }, [
    myClubActive,
    clubMatrixQuery.isSuccess,
    clubMatrixQuery.data,
    club,
    clubParam,
    searchParams,
    setSearchParams,
  ]);
  useEffect(() => {
    if (!teamSeasonsQuery.isSuccess || !team) return;
    if (season === "all") return;
    const seasons = teamSeasonsQuery.data ?? [];
    if (!seasons.includes(season)) {
      const next = new URLSearchParams(searchParams);
      next.delete("season");
      setSearchParams(next, { replace: true });
    }
  }, [
    teamSeasonsQuery.isSuccess,
    teamSeasonsQuery.data,
    season,
    team,
    searchParams,
    setSearchParams,
  ]);

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
    next.set("club", clubParam || resolvedClub || club);
    if (value) next.set("team", value);
    else next.delete("team");
    next.delete("season");
    setSearchParams(next, { replace: false });
  }

  function selectSeason(value: string) {
    const next = new URLSearchParams(searchParams);
    if (!value || value === "all") next.delete("season");
    else next.set("season", seasonForUrlQuery(value));
    setSearchParams(next, { replace: false });
  }

  const activeClub = resolvedClub || club;
  const matrixForClub =
    clubMatrixQuery.isSuccess &&
    clubMatrixQuery.data &&
    matrixPayloadMatchesClub(clubMatrixQuery.data, activeClub)
      ? clubMatrixQuery.data
      : undefined;
  const matrixRows = matrixForClub?.matrix.rows ?? [];
  const matrixSeasons = matrixForClub?.matrix.seasons ?? [];
  const matrixLoading =
    !!club &&
    (myClubActive
      ? clubMatrixQuery.isFetching || !matrixForClub
      : !clubsListQuery.isFetched || clubMatrixQuery.isFetching || !matrixForClub);
  const matrixError = !!club && clubMatrixQuery.isError;

  const showClubOverview = !!club && !team;
  const showTeamDetail = !!club && !!team;
  const showClubPicker = !myClubActive;
  const showFilterBar = showClubPicker || (club && clubTeams.length > 0);

  return (
    <div className="mx-auto max-w-[1280px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <header className="mb-6 lg:mb-8">
        <p className="text-label uppercase text-muted mb-2">{t("ui.team.eyebrow", "Akteure")}</p>
        <h1 className="text-h1">
          {t("ui.team.page_title", "Club")}
          {club ? (
            <>
              {" "}
              · <span className="font-normal text-muted">{resolvedClub || club}</span>
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

      {showFilterBar ? (
        <div className="sticky top-0 z-10 -mx-4 border-b border-border bg-background/85 px-4 py-3 backdrop-blur lg:-mx-8 lg:px-8">
          <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
            {showClubPicker ? (
              <FilterField label={t("ui.team.club", "Club")}>
                <ClubSearch
                  value={club}
                  clubs={clubs}
                  isLoading={clubsListQuery.isPending}
                  placeholder={t("ui.team.select_club", "Club eingeben oder wählen…")}
                  ariaLabel={t("ui.team.select_club", "Club wählen")}
                  clearAriaLabel={t("ui.team.clear_club", "Club-Auswahl löschen")}
                  onSelect={(c) => selectClub(c ?? "")}
                />
              </FilterField>
            ) : null}

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
      ) : null}

      <div className="mt-8 space-y-8">
        {!club && !myClubActive && (
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
            club={resolvedClub || club}
            teams={clubTeams}
            matrixRows={matrixRows}
            seasons={matrixSeasons}
            matrixLoading={matrixLoading}
            matrixError={matrixError}
            leagueLongNames={clubMatrixQuery.data?.league_long_names ?? {}}
            t={t}
          />
        )}

        {showTeamDetail && (
          <TeamDetail
            club={resolvedClub || club}
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

function matrixPayloadMatchesClub(data: ClubMatrixPayload, clubLabel: string): boolean {
  const fromApi = (data.selected_club || data.matrix.club || "").trim();
  if (!fromApi || !clubLabel) return false;
  return normalizeUnicodeLabel(fromApi) === normalizeUnicodeLabel(clubLabel);
}

function FilterField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-label text-muted">{label}</span>
      {children}
    </label>
  );
}
