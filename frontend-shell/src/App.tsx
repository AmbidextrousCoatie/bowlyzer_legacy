import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";

type OptionItem = { value: string; label: string };
type ApiResponse<T> = { success: true; data: T } | { success: false; error: { code: string; message: string } };

type ListData = { items: OptionItem[] };
type TableData = {
  title?: string;
  columns: Array<{ title: string; columns: Array<{ title: string; field: string }> }>;
  rows: Array<Record<string, unknown>>;
};
type ChartData = {
  title?: string;
  xAxis: { categories: Array<string | number> };
  series: Array<{ id: string; name: string; data: Array<number | null> }>;
};

const CHART_WIDTH = 900;
const CHART_HEIGHT = 280;
const COLORS = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c", "#0891b2"];

type ColorMode = "off" | "sequential" | "diverging";
type HeatmapNormMode = "global" | "row";
type HeatmapGroupingMode = "auto" | "single";
type TeamWeekView = "classic" | "individual" | "head-to-head";
type HonorItem = { label: string; value: string };
type HonorCardView = { title: string; items: HonorItem[]; raw?: unknown };

async function apiGet<T>(path: string, params: Record<string, string | undefined>): Promise<T> {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([k, v]) => {
    if (v && v.length > 0) url.searchParams.set(k, v);
  });
  const res = await fetch(url.pathname + url.search);
  const json = (await res.json()) as ApiResponse<T>;
  if (!("success" in json) || !json.success) {
    const message = "error" in json ? `${json.error.code}: ${json.error.message}` : "Unknown API error";
    throw new Error(message);
  }
  return json.data;
}

function App() {
  const initialParams = useMemo(() => new URLSearchParams(window.location.search), []);
  const [database, setDatabase] = useState(initialParams.get("database") ?? "");
  const [league, setLeague] = useState(initialParams.get("league") ?? "");
  const [season, setSeason] = useState(initialParams.get("season") ?? "");
  const [week, setWeek] = useState(initialParams.get("week") ?? "");
  const [team, setTeam] = useState(initialParams.get("team") ?? "");

  const [leagues, setLeagues] = useState<OptionItem[]>([]);
  const [seasons, setSeasons] = useState<OptionItem[]>([]);
  const [weeks, setWeeks] = useState<OptionItem[]>([]);
  const [teams, setTeams] = useState<OptionItem[]>([]);

  const [standings, setStandings] = useState<TableData | null>(null);
  const [pointsChart, setPointsChart] = useState<ChartData | null>(null);
  const [teamVsTeam, setTeamVsTeam] = useState<TableData | null>(null);
  const [matchdayStandings, setMatchdayStandings] = useState<TableData | null>(null);
  const [honorCards, setHonorCards] = useState<HonorCardView[]>([]);
  const [teamWeekView, setTeamWeekView] = useState<TeamWeekView>("classic");
  const [teamWeekTable, setTeamWeekTable] = useState<TableData | null>(null);
  const [heatmapNormMode, setHeatmapNormMode] = useState<HeatmapNormMode>("global");
  const [heatmapGroupingMode, setHeatmapGroupingMode] = useState<HeatmapGroupingMode>("auto");
  const [colorMode, setColorMode] = useState<ColorMode>("sequential");
  const [coreError, setCoreError] = useState<string | null>(null);
  const [matchdayError, setMatchdayError] = useState<string | null>(null);
  const [teamWeekError, setTeamWeekError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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

  useEffect(() => {
    apiGet<ListData>("/api/v1/league/options/leagues", { database })
      .then((d) => setLeagues(d.items))
      .catch((e: Error) => setCoreError(e.message));
  }, [database]);

  useEffect(() => {
    if (!league) return;
    apiGet<ListData>("/api/v1/league/options/seasons", { league, database })
      .then((d) => setSeasons(d.items))
      .catch((e: Error) => setCoreError(e.message));
  }, [league, database]);

  useEffect(() => {
    if (!league || !season) return;
    apiGet<ListData>("/api/v1/league/options/weeks", { league, season, database })
      .then((d) => setWeeks(d.items))
      .catch((e: Error) => setCoreError(e.message));
    apiGet<ListData>("/api/v1/league/options/teams", { league, season, database })
      .then((d) => setTeams(d.items))
      .catch((e: Error) => setCoreError(e.message));
  }, [league, season, database]);

  async function loadCoreViews() {
    if (!league || !season) return;
    setLoading(true);
    setCoreError(null);
    try {
      const [standingsData, pointsData] = await Promise.all([
        apiGet<TableData>("/api/v1/league/season/standings", { league, season, database }),
        apiGet<ChartData>("/api/v1/league/season/team-points", { league, season, week, database }),
      ]);
      setStandings(standingsData);
      setPointsChart(pointsData);
      const t2tData = await apiGet<TableData>("/api/v1/league/season/team-vs-team", {
        league,
        season,
        week,
        database,
      });
      setTeamVsTeam(t2tData);
    } catch (e) {
      setCoreError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function loadMatchdaySnapshot() {
    if (!league || !season || !week) return;
    setMatchdayError(null);
    try {
      const [standingsData, honorData] = await Promise.all([
        apiGet<TableData>("/api/v1/league/matchday/standings", { league, season, week, database }),
        apiGet<{ cards: unknown }>("/api/v1/league/matchday/honor-scores", {
          league,
          season,
          week,
          database,
        }),
      ]);
      setMatchdayStandings(standingsData);
      setHonorCards(normalizeHonorCards(honorData.cards));
    } catch (e) {
      setMatchdayError((e as Error).message);
    }
  }

  async function loadTeamWeekView(view: TeamWeekView) {
    if (!league || !season || !week || !team) return;
    setTeamWeekError(null);
    setTeamWeekView(view);
    try {
      let path = "/api/v1/league/team-week/classic";
      const params: Record<string, string | undefined> = { league, season, week, team, database };
      if (view === "individual") path = "/api/v1/league/team-week/individual-scores";
      if (view === "head-to-head") {
        path = "/api/v1/league/team-week/head-to-head";
        params.viewMode = "own_team";
      }
      const tableData = await apiGet<TableData>(path, params);
      setTeamWeekTable(tableData);
    } catch (e) {
      setTeamWeekError((e as Error).message);
    }
  }

  const standingsColumns = useMemo(() => {
    if (!standings) return [];
    return standings.columns.flatMap((g) => g.columns.map((c) => c.field));
  }, [standings]);

  const standingsColumnStats = useMemo(() => {
    if (!standings) return {};
    const stats: Record<string, { min: number; max: number; avg: number }> = {};
    standingsColumns.forEach((col) => {
      const values = standings.rows
        .map((r) => r[col])
        .filter((v): v is number => typeof v === "number");
      if (values.length > 1) {
        const min = Math.min(...values);
        const max = Math.max(...values);
        const avg = values.reduce((a, b) => a + b, 0) / values.length;
        stats[col] = { min, max, avg };
      }
    });
    return stats;
  }, [standings, standingsColumns]);

  function getConditionalCellStyle(
    value: unknown,
    col: string,
    mode: ColorMode,
  ): CSSProperties | undefined {
    if (mode === "off" || typeof value !== "number") return undefined;
    const stat = standingsColumnStats[col];
    if (!stat || stat.max === stat.min) return undefined;

    if (mode === "sequential") {
      const t = (value - stat.min) / (stat.max - stat.min);
      const bg = `rgba(37, 99, 235, ${0.12 + t * 0.55})`;
      return { backgroundColor: bg, color: t > 0.68 ? "#ffffff" : "#0f172a" };
    }

    const span = Math.max(Math.abs(stat.max - stat.avg), Math.abs(stat.min - stat.avg), 1);
    const t = (value - stat.avg) / span;
    if (t >= 0) {
      const alpha = 0.1 + Math.min(t, 1) * 0.55;
      return { backgroundColor: `rgba(22, 163, 74, ${alpha})`, color: t > 0.72 ? "#ffffff" : "#052e16" };
    }
    const alpha = 0.1 + Math.min(Math.abs(t), 1) * 0.55;
    return { backgroundColor: `rgba(220, 38, 38, ${alpha})`, color: Math.abs(t) > 0.72 ? "#ffffff" : "#450a0a" };
  }

  const chartGeometry = useMemo(() => {
    if (!pointsChart || pointsChart.series.length === 0) return null;
    const values = pointsChart.series.flatMap((s) => s.data).filter((v): v is number => typeof v === "number");
    if (values.length === 0) return null;

    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const xCount = Math.max(pointsChart.xAxis.categories.length - 1, 1);

    const seriesPaths = pointsChart.series.map((series, idx) => {
      const points = series.data
        .map((val, i) => {
          if (val === null) return null;
          const x = (i / xCount) * CHART_WIDTH;
          const y = CHART_HEIGHT - ((val - min) / range) * CHART_HEIGHT;
          return `${x},${y}`;
        })
        .filter((p): p is string => p !== null);
      return {
        name: series.name,
        color: COLORS[idx % COLORS.length],
        d: points.join(" "),
      };
    });

    return { min, max, seriesPaths };
  }, [pointsChart]);

  const heatmapModel = useMemo(() => {
    if (!teamVsTeam) return null;
    const fields = teamVsTeam.columns.flatMap((g) => g.columns.map((c) => c.field));
    if (fields.length < 2) return null;
    const rowLabelField = fields[0];
    const valueFields = fields.slice(1);

    const columnStats = valueFields
      .map((field) => {
        const values = teamVsTeam.rows
          .map((r) => r[field])
          .filter((v): v is number => typeof v === "number");
        if (values.length === 0) return null;
        const min = Math.min(...values);
        const max = Math.max(...values);
        const avg = values.reduce((a, b) => a + b, 0) / values.length;
        const magnitude = Math.floor(Math.log10(Math.max(Math.abs(min), Math.abs(max), 1)));
        return { field, min, max, avg, magnitude };
      })
      .filter((s): s is { field: string; min: number; max: number; avg: number; magnitude: number } => s !== null);

    const groupedFields = new Map<string, string[]>();
    if (heatmapGroupingMode === "single") {
      groupedFields.set("all-metrics", columnStats.map((s) => s.field));
    } else {
      // Auto grouping: split by known semantic hints first, then by magnitude bucket.
      columnStats.forEach((s) => {
        const lower = s.field.toLowerCase();
        if (lower.includes("point")) {
          const list = groupedFields.get("points") ?? [];
          list.push(s.field);
          groupedFields.set("points", list);
          return;
        }
        if (lower.includes("score") || lower.includes("avg") || lower.includes("average")) {
          const list = groupedFields.get("scores") ?? [];
          list.push(s.field);
          groupedFields.set("scores", list);
          return;
        }
        const key = `scale-10^${s.magnitude}`;
        const list = groupedFields.get(key) ?? [];
        list.push(s.field);
        groupedFields.set(key, list);
      });
    }

    const groups = Array.from(groupedFields.entries()).map(([name, fieldsInGroup]) => {
      const values = teamVsTeam.rows
        .flatMap((r) => fieldsInGroup.map((f) => r[f]))
        .filter((v): v is number => typeof v === "number");
      const min = values.length > 0 ? Math.min(...values) : 0;
      const max = values.length > 0 ? Math.max(...values) : 1;
      return { name, fields: fieldsInGroup, min, max };
    });

    return { rowLabelField, groups };
  }, [teamVsTeam, heatmapGroupingMode]);

  function getHeatColor(value: unknown, rowValues: number[] | null, groupMin: number, groupMax: number): CSSProperties | undefined {
    if (typeof value !== "number" || !heatmapModel) return undefined;
    const min = heatmapNormMode === "row" && rowValues && rowValues.length > 0 ? Math.min(...rowValues) : groupMin;
    const max = heatmapNormMode === "row" && rowValues && rowValues.length > 0 ? Math.max(...rowValues) : groupMax;
    const range = max - min || 1;
    const t = (value - min) / range;
    const alpha = 0.08 + t * 0.62;
    return { backgroundColor: `rgba(14, 116, 144, ${alpha})`, color: t > 0.65 ? "#ffffff" : "#083344" };
  }

  return (
    <main className="app">
      <h1>Bowlyzer Frontend Shell</h1>
      <p className="sub">Minimal React shell wired to League API v1</p>

      <section className="panel">
        <h2>Filters</h2>
        <div className="grid">
          <label>
            Database
            <input value={database} onChange={(e) => setDatabase(e.target.value)} placeholder="optional" />
          </label>
          <label>
            League
            <select value={league} onChange={(e) => setLeague(e.target.value)}>
              <option value="">Select...</option>
              {leagues.map((i) => (
                <option key={i.value} value={i.value}>
                  {i.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Season
            <select value={season} onChange={(e) => setSeason(e.target.value)}>
              <option value="">Select...</option>
              {seasons.map((i) => (
                <option key={i.value} value={i.value}>
                  {i.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Week
            <select value={week} onChange={(e) => setWeek(e.target.value)}>
              <option value="">Optional...</option>
              {weeks.map((i) => (
                <option key={i.value} value={i.value}>
                  {i.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Team
            <select value={team} onChange={(e) => setTeam(e.target.value)}>
              <option value="">Optional...</option>
              {teams.map((i) => (
                <option key={i.value} value={i.value}>
                  {i.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <button onClick={loadCoreViews} disabled={!league || !season || loading}>
          {loading ? "Loading..." : "Load Season Views"}
        </button>
        <button onClick={loadMatchdaySnapshot} disabled={!league || !season || !week} style={{ marginLeft: 8 }}>
          Load Matchday Snapshot
        </button>
        <button
          onClick={() => loadTeamWeekView(teamWeekView)}
          disabled={!league || !season || !week || !team}
          style={{ marginLeft: 8 }}
        >
          Load Team Week
        </button>
      </section>

      {coreError && <p className="error">{coreError}</p>}

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
          <table>
            <thead>
              <tr>{standingsColumns.map((c) => <th key={c}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {standings.rows.slice(0, 10).map((row, idx) => (
                <tr key={idx}>
                  {standingsColumns.map((c) => (
                    <td key={`${idx}-${c}`} style={getConditionalCellStyle(row[c], c, colorMode)}>
                      {String(row[c] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel">
        <h2>Team Points (v1 line chart)</h2>
        {!pointsChart || !chartGeometry ? (
          <p>No chart payload loaded yet.</p>
        ) : (
          <>
            <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} className="lineChart" role="img" aria-label="Team points line chart">
              {chartGeometry.seriesPaths.map((s) => (
                <polyline
                  key={s.name}
                  points={s.d}
                  fill="none"
                  stroke={s.color}
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              ))}
            </svg>
            <div className="legend">
              {chartGeometry.seriesPaths.map((s) => (
                <span key={`legend-${s.name}`} className="legendItem">
                  <i style={{ backgroundColor: s.color }} />
                  {s.name}
                </span>
              ))}
            </div>
            <p className="axisHint">
              y range: {chartGeometry.min.toFixed(2)} - {chartGeometry.max.toFixed(2)}
            </p>
            <details>
              <summary>Raw chart payload</summary>
              <pre>{JSON.stringify(pointsChart, null, 2)}</pre>
            </details>
          </>
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
                        return (
                          <tr key={`hm-r-${group.name}-${idx}`}>
                            <td>{String(row[heatmapModel.rowLabelField] ?? "")}</td>
                            {group.fields.map((f) => (
                              <td
                                key={`hm-${group.name}-${idx}-${f}`}
                                style={getHeatColor(row[f], rowValues, group.min, group.max)}
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
        {!matchdayStandings ? (
          <p>Select week and click "Load Matchday Snapshot".</p>
        ) : (
          <>
            <h3 className="groupTitle">Week Standings</h3>
            <SimpleTable table={matchdayStandings} />
            <h3 className="groupTitle">Honor Scores</h3>
            {honorCards.length === 0 ? (
              <p>No honor cards available.</p>
            ) : (
              <div className="cardsGrid">
                {honorCards.map((card, idx) => (
                  <div key={`hc-${idx}`} className="honorCard">
                    <h4>{card.title}</h4>
                    {card.items.length > 0 ? (
                      <ul>
                        {card.items.map((it, itIdx) => (
                          <li key={`hc-item-${idx}-${itIdx}`}>
                            <strong>{it.label}:</strong> {it.value}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <pre>{JSON.stringify(card.raw ?? {}, null, 2)}</pre>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </section>

      <section className="panel">
        <h2>Team Week Details (v1)</h2>
        <div className="toolbar">
          <button type="button" onClick={() => void loadTeamWeekView("classic")} disabled={!league || !season || !week || !team}>
            Classic
          </button>
          <button
            type="button"
            onClick={() => void loadTeamWeekView("individual")}
            disabled={!league || !season || !week || !team}
          >
            Individual Scores
          </button>
          <button
            type="button"
            onClick={() => void loadTeamWeekView("head-to-head")}
            disabled={!league || !season || !week || !team}
          >
            Head-to-Head
          </button>
        </div>
        <p className="axisHint">Active view: {teamWeekView}</p>
        {teamWeekError && <p className="error">{teamWeekError}</p>}
        {!teamWeekTable ? <p>Select team + week and load a team-week view.</p> : <SimpleTable table={teamWeekTable} />}
      </section>
    </main>
  );
}

function SimpleTable({ table }: { table: TableData }) {
  const columns = table.columns.flatMap((g) => g.columns.map((c) => c.field));
  return (
    <div className="heatmapWrap">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={`st-h-${c}`}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, idx) => (
            <tr key={`st-r-${idx}`}>
              {columns.map((c) => (
                <td key={`st-c-${idx}-${c}`}>{String(row[c] ?? "")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function normalizeHonorCards(raw: unknown): HonorCardView[] {
  if (Array.isArray(raw)) {
    return raw.map((item, idx) => normalizeSingleHonorCard(item, `Card ${idx + 1}`));
  }
  if (raw && typeof raw === "object") {
    return Object.entries(raw as Record<string, unknown>).map(([key, value]) =>
      normalizeSingleHonorCard(value, prettifyKey(key)),
    );
  }
  return [];
}

function normalizeSingleHonorCard(rawCard: unknown, fallbackTitle: string): HonorCardView {
  if (!rawCard || typeof rawCard !== "object") {
    return { title: fallbackTitle, items: [], raw: rawCard };
  }
  const obj = rawCard as Record<string, unknown>;
  const title =
    (typeof obj.title === "string" && obj.title) ||
    (typeof obj.name === "string" && obj.name) ||
    fallbackTitle;

  const items: HonorItem[] = [];
  Object.entries(obj).forEach(([key, value]) => {
    if (key === "title" || key === "name") return;
    if (Array.isArray(value)) {
      value.forEach((entry, idx) => {
        if (entry && typeof entry === "object") {
          const text = summarizeObject(entry as Record<string, unknown>);
          items.push({ label: `${prettifyKey(key)} #${idx + 1}`, value: text });
        } else {
          items.push({ label: `${prettifyKey(key)} #${idx + 1}`, value: String(entry) });
        }
      });
      return;
    }
    if (value && typeof value === "object") {
      items.push({ label: prettifyKey(key), value: summarizeObject(value as Record<string, unknown>) });
      return;
    }
    items.push({ label: prettifyKey(key), value: String(value) });
  });

  return { title, items, raw: rawCard };
}

function summarizeObject(obj: Record<string, unknown>): string {
  const preferredKeys = ["player", "team", "name", "score", "average", "points", "value"];
  const preferred = preferredKeys
    .map((k) => obj[k])
    .filter((v) => v !== undefined && v !== null)
    .map((v) => String(v));
  if (preferred.length > 0) return preferred.join(" | ");
  return Object.entries(obj)
    .slice(0, 4)
    .map(([k, v]) => `${prettifyKey(k)}: ${String(v)}`)
    .join(", ");
}

function prettifyKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default App;
