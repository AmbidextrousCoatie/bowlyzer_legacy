import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import type { ColorMode, HeatmapGroupingMode, HeatmapNormMode } from "./types";
import FilterBar from "./components/FilterBar";
import HoverTooltip from "./components/HoverTooltip";
import { useCoreViews, useLeagueOptions, useMatchdayViews, useTeamWeekViews } from "./hooks/useLeagueData";
import { useConditionalColoring } from "./hooks/useConditionalColoring";
import { useHeatmapModel } from "./hooks/useHeatmapModel";
import { useHoverTooltip } from "./hooks/useHoverTooltip";
import {
  buildTeamColorMap,
  lookupTeamColor,
  orderedTeamNamesForPalette,
  orderedTeamNamesFromPointsChartSeries,
  type TeamPaletteName,
} from "./lib/teamColors";
import { THEME } from "./lib/theme";

const TabulatorTable = lazy(() => import("./components/TabulatorTable"));
const LegacyPortTable = lazy(() => import("./components/LegacyPortTable"));
const HonorCards = lazy(() => import("./components/HonorCards"));
const EChartPanel = lazy(() => import("./components/EChartPanel"));

function App() {
  const initialParams = useMemo(() => new URLSearchParams(window.location.search), []);
  const [database, setDatabase] = useState(initialParams.get("database") ?? "");
  const [league, setLeague] = useState(initialParams.get("league") ?? "");
  const [season, setSeason] = useState(initialParams.get("season") ?? "");
  const [week, setWeek] = useState(initialParams.get("week") ?? "");
  const [team, setTeam] = useState(initialParams.get("team") ?? "");
  const [teamPalette, setTeamPalette] = useState<TeamPaletteName>("rainbowPastel");
  const [firstColTeamMarkup, setFirstColTeamMarkup] = useState(true);

  const { leagues, seasons, weeks, teams, error: optionsError } = useLeagueOptions({ database, league, season });
  const {
    standings,
    pointsChart,
    teamVsTeam,
    loading,
    error: coreError,
    refresh: refreshCoreViews,
  } = useCoreViews({ database, league, season, week });
  const {
    matchdayStandings,
    honorCards,
    loading: matchdayLoading,
    error: matchdayError,
    refresh: refreshMatchdayViews,
  } = useMatchdayViews({ database, league, season, week });
  const {
    teamWeekView,
    teamWeekTable,
    loading: teamWeekLoading,
    error: teamWeekError,
    refresh: refreshTeamWeekView,
  } = useTeamWeekViews({ database, league, season, week, team });

  const [heatmapNormMode, setHeatmapNormMode] = useState<HeatmapNormMode>("global");
  const [heatmapGroupingMode, setHeatmapGroupingMode] = useState<HeatmapGroupingMode>("auto");
  const [colorMode, setColorMode] = useState<ColorMode>("sequential");
  const { tooltip: heatTooltip, onEnter: onHeatEnter, onMove: onHeatMove, onLeave: onHeatLeave } = useHoverTooltip();

  useEffect(() => {
    const params = new URLSearchParams();
    if (database) params.set("database", database);
    if (league) params.set("league", league);
    if (season) params.set("season", season);
    if (week) params.set("week", week);
    if (team) params.set("team", team);
    const query = params.toString();
    const next = query.length > 0 ? `?${query}` : window.location.pathname;
    window.history.replaceState({}, "", next);
  }, [database, league, season, week, team]);

  const { getConditionalCellStyle } = useConditionalColoring(standings);
  const { heatmapModel, getHeatColor } = useHeatmapModel(teamVsTeam, heatmapGroupingMode, heatmapNormMode);

  const teamOrder = useMemo(() => {
    if (pointsChart?.series?.length) {
      return orderedTeamNamesFromPointsChartSeries(pointsChart.series);
    }
    if (standings?.rows?.length) {
      return orderedTeamNamesForPalette(standings.rows);
    }
    if (matchdayStandings?.rows?.length) {
      return orderedTeamNamesForPalette(matchdayStandings.rows);
    }
    return [];
  }, [pointsChart, standings, matchdayStandings]);

  const teamColors = useMemo(() => buildTeamColorMap(teamOrder, teamPalette), [teamOrder, teamPalette]);

  return (
    <main className="app">
      <h1>Bowlyzer Frontend Shell</h1>
      <p className="sub">Minimal React shell wired to League API v1</p>

      <FilterBar
        database={database}
        league={league}
        season={season}
        week={week}
        team={team}
        teamPalette={teamPalette}
        firstColTeamMarkup={firstColTeamMarkup}
        leagues={leagues}
        seasons={seasons}
        weeks={weeks}
        teams={teams}
        coreLoading={loading}
        matchdayLoading={matchdayLoading}
        teamWeekLoading={teamWeekLoading}
        onDatabaseChange={setDatabase}
        onLeagueChange={setLeague}
        onSeasonChange={setSeason}
        onWeekChange={setWeek}
        onTeamChange={setTeam}
        onTeamPaletteChange={setTeamPalette}
        onFirstColTeamMarkupChange={setFirstColTeamMarkup}
        onRefreshCore={() => void refreshCoreViews()}
        onRefreshMatchday={() => void refreshMatchdayViews()}
        onRefreshTeamWeek={() => void refreshTeamWeekView(teamWeekView)}
      />

      {(optionsError || coreError) && <p className="error">{optionsError ?? coreError}</p>}

      <section className="panel">
        <h2>Standings (v1 table)</h2>
        <div className="toolbar">
          <label>
            Conditional coloring
            <select value={colorMode} onChange={(e) => setColorMode(e.target.value as ColorMode)}>
              <option value="off">off</option>
              <option value="sequential">sequential</option>
              <option value="diverging">diverging</option>
            </select>
          </label>
        </div>
        {!standings ? (
          <p>Load season views to display standings.</p>
        ) : (
          <>
            <Suspense fallback={<p className="axisHint loading">Loading table...</p>}>
              <TabulatorTable
                table={standings}
                cellStyle={(value, col) => getConditionalCellStyle(value, col, colorMode)}
                teamColors={teamColors}
                useTeamColorFirstColumn={firstColTeamMarkup}
                paginate={false}
              />
            </Suspense>
            <h3 className="groupTitle">Legacy Port Renderer (comparison)</h3>
            <Suspense fallback={<p className="axisHint loading">Loading legacy renderer...</p>}>
              <LegacyPortTable table={standings} />
            </Suspense>
          </>
        )}
      </section>

      <section className="panel">
        {!pointsChart ? (
          <p>No chart payload loaded yet.</p>
        ) : (
          <Suspense fallback={<p className="axisHint loading">Loading chart...</p>}>
            <EChartPanel
              title="Team Points (v1 line chart)"
              chart={pointsChart}
              teamColors={teamColors}
              rawPayload={pointsChart}
            />
          </Suspense>
        )}
      </section>

      <section className="panel">
        <h2>Team vs Team Heatmap (v1)</h2>
        <div className="toolbar">
          <label>
            Normalization
            <select value={heatmapNormMode} onChange={(e) => setHeatmapNormMode(e.target.value as HeatmapNormMode)}>
              <option value="global">global</option>
              <option value="row">row</option>
            </select>
          </label>
          <label>
            Grouping
            <select value={heatmapGroupingMode} onChange={(e) => setHeatmapGroupingMode(e.target.value as HeatmapGroupingMode)}>
              <option value="auto">auto (split by metric scale/type)</option>
              <option value="single">single (all metrics)</option>
            </select>
          </label>
        </div>
        {!teamVsTeam || !heatmapModel ? (
          <p>Load season views to display team-vs-team heatmap.</p>
        ) : (
          <>
            {heatmapModel.groups.map((group) => (
              <div key={`group-${group.name}`} className="heatmapGroup">
                <h3 className="groupTitle">{group.name}</h3>
                <div className="heatmapWrap">
                  <table>
                    <thead>
                      <tr>
                        <th>{heatmapModel.rowLabelField}</th>
                        {group.fields.map((f) => (
                          <th key={`h-${group.name}-${f}`}>{f}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {teamVsTeam.rows.map((row, idx) => {
                        const rowValues = group.fields
                          .map((f) => row[f])
                          .filter((v): v is number => typeof v === "number");
                        const rowLabel = String(row[heatmapModel.rowLabelField] ?? "");
                        return (
                          <tr key={`hm-r-${group.name}-${idx}`}>
                            <td>
                              <span className="firstColWithTeamColor">
                                <span
                                  className="teamColorDot"
                                  style={{
                                    backgroundColor: lookupTeamColor(teamColors, rowLabel) ?? THEME.fallback.teamDot,
                                  }}
                                  aria-hidden="true"
                                />
                                <span>{rowLabel}</span>
                              </span>
                            </td>
                            {group.fields.map((f) => (
                              <td
                                key={`hm-${group.name}-${idx}-${f}`}
                                className={heatTooltip.cellKey === `${group.name}-${idx}-${f}` ? "heatCellActive" : undefined}
                                style={getHeatColor(row[f], rowValues, group.min, group.max)}
                                onMouseEnter={(e) => {
                                  onHeatEnter(
                                    e,
                                    `${rowLabel} vs ${f}: ${String(row[f] ?? "n/a")} (range ${group.min.toFixed(2)} - ${group.max.toFixed(2)})`,
                                    `${group.name}-${idx}-${f}`,
                                  );
                                }}
                                onMouseMove={onHeatMove}
                                onMouseLeave={onHeatLeave}
                              >
                                {String(row[f] ?? "")}
                              </td>
                            ))}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="heatLegend">
                  <div className="heatLegendBar" aria-hidden="true" />
                  <div className="heatLegendLabels">
                    <span>{group.min.toFixed(2)}</span>
                    <span>{group.max.toFixed(2)}</span>
                  </div>
                </div>
                <p className="axisHint">
                  {group.name} range: {group.min.toFixed(2)} - {group.max.toFixed(2)}
                </p>
              </div>
            ))}
          </>
        )}
      </section>

      <section className="panel">
        <h2>Matchday Snapshot (v1)</h2>
        {matchdayError && <p className="error">{matchdayError}</p>}
        {matchdayLoading ? <p className="axisHint loading">Refreshing matchday snapshot...</p> : null}
        {!matchdayStandings ? (
          <p>Select week and click "Load Matchday Snapshot".</p>
        ) : (
          <>
            <h3 className="groupTitle">Week Standings</h3>
            <Suspense fallback={<p className="axisHint loading">Loading table...</p>}>
              <TabulatorTable
                table={matchdayStandings}
                teamColors={teamColors}
                useTeamColorFirstColumn={firstColTeamMarkup}
                paginate={false}
              />
            </Suspense>
            <h3 className="groupTitle">Honor Scores</h3>
            <Suspense fallback={<p className="axisHint loading">Loading cards...</p>}>
              <HonorCards cards={honorCards} />
            </Suspense>
          </>
        )}
      </section>

      <section className="panel">
        <h2>Team Week Details (v1)</h2>
        <div className="toolbar">
          <button
            type="button"
            onClick={() => void refreshTeamWeekView("classic")}
            disabled={!league || !season || !week || !team || teamWeekLoading}
          >
            Classic
          </button>
          <button
            type="button"
            onClick={() => void refreshTeamWeekView("individual")}
            disabled={!league || !season || !week || !team || teamWeekLoading}
          >
            Individual Scores
          </button>
          <button
            type="button"
            onClick={() => void refreshTeamWeekView("head-to-head")}
            disabled={!league || !season || !week || !team || teamWeekLoading}
          >
            Head-to-Head
          </button>
        </div>
        {teamWeekLoading ? <p className="axisHint loading">Refreshing team-week details...</p> : null}
        <p className="axisHint">Active view: {teamWeekView}</p>
        {teamWeekError && <p className="error">{teamWeekError}</p>}
        {!teamWeekTable ? (
          <p>Select team + week and load a team-week view.</p>
        ) : (
          <Suspense fallback={<p className="axisHint loading">Loading table...</p>}>
            <TabulatorTable
              table={teamWeekTable}
              teamColors={teamColors}
              useTeamColorFirstColumn={firstColTeamMarkup}
              paginate={false}
            />
          </Suspense>
        )}
      </section>

      <HoverTooltip visible={heatTooltip.visible} x={heatTooltip.x} y={heatTooltip.y} content={heatTooltip.content} />
    </main>
  );
}

export default App;
