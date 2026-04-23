(function () {
  function compactClubName(club) {
    if (!club) return "";
    const text = String(club);
    const sep = " - ";
    const idx = text.indexOf(sep);
    if (idx >= 0 && idx + sep.length < text.length) {
      return text.slice(idx + sep.length).trim();
    }
    return text;
  }

  function getCurrentDatabase() {
    const params = new URLSearchParams(window.location.search);
    return params.get("database");
  }

  function withDatabase(url) {
    const database = getCurrentDatabase();
    if (!database) return url;
    const joiner = url.includes("?") ? "&" : "?";
    return `${url}${joiner}database=${encodeURIComponent(database)}`;
  }

  async function fetchJson(url) {
    const res = await fetch(withDatabase(url));
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    return await res.json();
  }

  function renderCards(cards) {
    const container = document.getElementById("tournamentCards");
    if (!container) return;
    if (!cards || cards.length === 0) {
      container.innerHTML = '<div class="col-12"><div class="alert alert-info">No summary cards available.</div></div>';
      return;
    }
    const tournamentCard = cards.find((c) => String(c.title || "").toLowerCase() === "tournament");
    const titleText = tournamentCard
      ? `${tournamentCard.value ?? "Tournament"}${tournamentCard.subtitle ? ` - ${tournamentCard.subtitle}` : ""}`
      : "Tournament Overview";
    const innerCards = cards.filter((c) => c !== tournamentCard);

    container.innerHTML = `
      <div class="card mb-4">
        <div class="card-header">
          <h5 class="mb-0">${titleText}</h5>
        </div>
        <div class="card-body">
          <div class="row g-3">
            ${innerCards
              .map(
                (card, idx) => `
                <div class="col-md-3">
                  <div class="card h-100" id="tournamentOverviewStatCard_${idx}">
                    <div class="card-header"><h6 class="mb-0">${card.title || ""}</h6></div>
                    <div class="card-body">
                      <div class="h5 mb-1">${card.value ?? ""}</div>
                      <small class="text-muted">${card.subtitle || ""}</small>
                    </div>
                  </div>
                </div>
              `
              )
              .join("")}
          </div>
        </div>
      </div>
    `;

    // Highlight winner card with green/yellow palette (less purple).
    innerCards.forEach((card, idx) => {
      const title = String(card.title || "").toLowerCase();
      if (!title.includes("leader") && !title.includes("winner")) return;
      const el = document.getElementById(`tournamentOverviewStatCard_${idx}`);
      if (!el) return;
      const winnerColor = "#9bbf30"; // green/yellow from scheme family
      el.style.border = `2px solid ${winnerColor}`;
      el.style.background = `linear-gradient(180deg, ${winnerColor}22 0%, transparent 100%)`;
      const header = el.querySelector(".card-header");
      if (header) {
        header.style.backgroundColor = winnerColor;
        header.style.color = "#132";
      }
    });
  }

  function renderTable(containerId, tableData) {
    if (typeof createTableTabulator === "function") {
      createTableTabulator(containerId, tableData, {
        disablePositionCircle: true,
        enableSpecialRowStyling: true,
        tooltips: true,
      });
      return;
    }
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '<div class="alert alert-warning">Tabulator renderer unavailable.</div>';
  }

  function renderEffortRows(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return '<div class="text-muted">No entries</div>';
    }
    return items
      .map(
        (entry) => `
          <div class="d-flex justify-content-between">
            <span>${entry.player || "Unknown"}${entry.club ? ` (${compactClubName(entry.club)})` : ""}</span>
            <strong>${entry.display_value ?? entry.value ?? ""}</strong>
          </div>
        `
      )
      .join("");
  }

  function renderBestEfforts(bestEfforts) {
    const container = document.getElementById("tournamentBestEfforts");
    if (!container) return;
    const sections = bestEfforts?.sections || [];
    const n = bestEfforts?.n || 5;
    if (!sections.length) {
      container.innerHTML = "";
      return;
    }

    container.innerHTML = `
      <div class="card">
        <div class="card-header">
          <h5>Best Efforts (Top ${n})</h5>
        </div>
        <div class="card-body">
          <div class="row g-3">
            ${sections
              .map(
                (section) => `
                <div class="col-lg-6">
                  <div class="card h-100">
                    <div class="card-header">
                      <h6>${section.scope || "Scope"}</h6>
                    </div>
                    <div class="card-body">
                      <div class="mb-3">
                        <h6 class="text-muted">Best Games</h6>
                        ${renderEffortRows(section.best_games)}
                      </div>
                      <div class="mb-3">
                        <h6 class="text-muted">Best Pairs</h6>
                        ${renderEffortRows(section.best_pairs)}
                      </div>
                      <div>
                        <h6 class="text-muted">Best Blocks</h6>
                        ${renderEffortRows(section.best_blocks)}
                      </div>
                    </div>
                  </div>
                </div>
              `
              )
              .join("")}
          </div>
        </div>
      </div>
    `;
  }

  let tournamentPlayers = [];
  function setPlayerMode(enabled) {
    const ids = ["tournamentCards", "tournamentBestEfforts", "tournamentLeaderboardCard", "tournamentRoundResultsCard"];
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.style.display = enabled ? "none" : "";
    });
  }

  async function loadPlayers(season, tournament) {
    const list = document.getElementById("tournamentPlayersList");
    const input = document.getElementById("tournamentPlayerInput");
    if (!list || !input || !tournament) return;
    try {
      tournamentPlayers = await fetchJson(
        `/tournament/get_available_players?season=${encodeURIComponent(season)}&tournament=${encodeURIComponent(tournament)}`
      );
      list.innerHTML = (tournamentPlayers || [])
        .map((p) => `<option value="${p}"></option>`)
        .join("");
      input.value = "";
      renderPlayerSection(null);
    } catch (err) {
      console.error("Failed to load players:", err);
      tournamentPlayers = [];
      list.innerHTML = "";
      renderPlayerSection(null);
    }
  }

  function renderPlayerSection(payload) {
    const container = document.getElementById("tournamentPlayerSection");
    if (!container) return;
    if (!payload || !payload.player) {
      container.innerHTML = "";
      return;
    }

    container.innerHTML = `
      <div class="card mb-4">
        <div class="card-header">
          <div class="d-flex flex-wrap justify-content-between align-items-center gap-2">
            <h5 class="mb-0">${payload.player}${payload.player_club ? ` (${payload.player_club})` : ""}</h5>
            <button id="tournamentBackToOverviewBtn" class="btn btn-sm btn-primary">Back to Tournament Overview</button>
          </div>
        </div>
        <div class="card-body">
          <div class="row g-3 mb-3">
            <div class="col-md-4">
              <div class="card h-100" id="tournamentFinalPositionCard">
                <div class="card-header"><h6>Final Position</h6></div>
                <div class="card-body">
                  <div class="h5 mb-1">${payload.summary?.final_position ?? "-"}</div>
                  <small class="text-muted">After final game</small>
                </div>
              </div>
            </div>
            <div class="col-md-4">
              <div class="card h-100">
                <div class="card-header"><h6>Average</h6></div>
                <div class="card-body">
                  <div class="h5 mb-1">${payload.summary?.average ?? "-"}</div>
                  <small class="text-muted">Cumulated</small>
                </div>
              </div>
            </div>
            <div class="col-md-4">
              <div class="card h-100">
                <div class="card-header"><h6>Best Position</h6></div>
                <div class="card-body">
                  <div class="h5 mb-1">${payload.summary?.best_position ?? "-"}</div>
                  <small class="text-muted">${payload.summary?.best_position_game ?? ""}</small>
                </div>
              </div>
            </div>
          </div>
          <div class="row g-3 mb-3">
            <div class="col-md-4">
              <div class="card h-100">
                <div class="card-header"><h6>Highest Game</h6></div>
                <div class="card-body">
                  <div class="h5 mb-1">${payload.best_efforts?.highest_game?.score ?? "-"}</div>
                  <small class="text-muted">${payload.best_efforts?.highest_game?.stage || ""} ${payload.best_efforts?.highest_game?.game ? `(G${payload.best_efforts.highest_game.game})` : ""}</small>
                </div>
              </div>
            </div>
            <div class="col-md-4">
              <div class="card h-100">
                <div class="card-header"><h6>Highest Pair</h6></div>
                <div class="card-body">
                  <div class="h5 mb-1">${payload.best_efforts?.highest_pair?.score ?? "-"}</div>
                  <small class="text-muted">${payload.best_efforts?.highest_pair?.stage || ""} ${payload.best_efforts?.highest_pair?.pair ? `(${payload.best_efforts.highest_pair.pair})` : ""}</small>
                </div>
              </div>
            </div>
            <div class="col-md-4">
              <div class="card h-100">
                <div class="card-header"><h6>Highest Block</h6></div>
                <div class="card-body">
                  <div class="h5 mb-1">${payload.best_efforts?.highest_block?.score ?? "-"}</div>
                  <small class="text-muted">${payload.best_efforts?.highest_block?.stage || ""}</small>
                </div>
              </div>
            </div>
          </div>
          <div class="row g-3 mb-3">
            <div class="col-md-6">
              <div class="card h-100">
                <div class="card-header"><h6>Cumulated Average Over Games</h6></div>
                <div class="card-body">
                  <div id="tournamentPlayerAvgChart" style="width:100%; min-width:100%; height:280px;"></div>
                </div>
              </div>
            </div>
            <div class="col-md-6">
              <div class="card h-100">
                <div class="card-header"><h6>Cumulated Position Over Games</h6></div>
                <div class="card-body">
                  <div id="tournamentPlayerPosChart" style="width:100%; min-width:100%; height:280px;"></div>
                </div>
              </div>
            </div>
          </div>
          <div class="d-flex justify-content-center mb-3">
            <div id="tournamentPlayerChartsLegend" class="d-flex flex-wrap justify-content-center gap-3"></div>
          </div>
          <div id="tournamentPlayerRoundTable"></div>
        </div>
      </div>
    `;
    // Highlight final-position tile with theme semantic color.
    const finalCard = document.getElementById("tournamentFinalPositionCard");
    if (finalCard) {
      const highlight = "#9bbf30"; // green/yellow highlight
      finalCard.style.border = `2px solid ${highlight}`;
      finalCard.style.background = `linear-gradient(180deg, ${highlight}22 0%, transparent 100%)`;
      const header = finalCard.querySelector(".card-header");
      if (header) {
        header.style.backgroundColor = highlight;
        header.style.color = "#111";
        const h6 = header.querySelector("h6");
        if (h6) h6.style.marginBottom = "0";
      }
    }
    renderTable("tournamentPlayerRoundTable", payload.round_table);
    renderPlayerProgressCharts(payload.progress_series, payload.player);
    document.getElementById("tournamentBackToOverviewBtn")?.addEventListener("click", () => {
      const input = document.getElementById("tournamentPlayerInput");
      if (input) input.value = "";
      setPlayerMode(false);
      renderPlayerSection(null);
    });
  }

  function renderPlayerProgressCharts(series, playerName) {
    if (!series || !Array.isArray(series.labels) || series.labels.length === 0) return;
    if (typeof echarts === "undefined") {
      console.warn("echarts unavailable; player charts cannot render.");
      return;
    }
    const totalGames = series.labels.length;
    const gameLabels = Array.from({ length: totalGames }, (_, i) => i + 1);
    const roundEnds = (series.round_end_lines || [])
      .map((v) => Number(v))
      .filter((v) => Number.isFinite(v) && v >= 1 && v <= totalGames);

    const renderLine = (containerId, dataSeries, yName, yMin, yMax, invertY, cutLines) => {
      const container = document.getElementById(containerId);
      if (!container) return;
      const existing = echarts.getInstanceByDom(container);
      if (existing) existing.dispose();
      const chart = echarts.init(container, null, { renderer: "canvas", devicePixelRatio: window.devicePixelRatio });
      const colorPlayer =
        (window.ColorUtils && typeof window.ColorUtils.getThemeColor === "function" && window.ColorUtils.getThemeColor("primary")) ||
        "#1f77b4";
      const colorRoundBoundary =
        (window.ColorUtils && typeof window.ColorUtils.getThemeColor === "function" && window.ColorUtils.getThemeColor("border")) ||
        "rgba(0,0,0,0.25)";
      const colorCutQualifying =
        (typeof getSemanticColor === "function" && getSemanticColor("negative")) || "#D62728";
      const colorCutRound2 =
        (typeof getSemanticColor === "function" && getSemanticColor("highlight")) || "#ffb000";

      const clamped = (dataSeries || []).map((v) => {
        const n = Number(v);
        if (!Number.isFinite(n)) return null;
        return Math.max(yMin, Math.min(yMax, n));
      });

      const markLines = [];
      // Vertical round separators
      roundEnds.forEach((x) => {
        markLines.push({ xAxis: x, lineStyle: { color: colorRoundBoundary, type: "solid", width: 1 } });
      });
      // Horizontal cut/reference lines
      const cutValues = (cutLines || [])
        .map((v) => Number(v))
        .filter((v) => Number.isFinite(v));
      if (cutValues.length > 0) {
        const y = Math.max(yMin, Math.min(yMax, cutValues[0]));
        markLines.push({ yAxis: y, lineStyle: { color: colorCutQualifying, type: "dashed", width: 2 } });
      }
      if (cutValues.length > 1) {
        const y = Math.max(yMin, Math.min(yMax, cutValues[1]));
        markLines.push({ yAxis: y, lineStyle: { color: colorCutRound2, type: "dashed", width: 2 } });
      }

      chart.setOption(
        {
          animation: false,
          tooltip: { trigger: "axis" },
          legend: { show: false },
          grid: { top: "10%", right: "5%", bottom: "14%", left: "10%", containLabel: true },
          xAxis: {
            type: "category",
            name: "Game",
            nameLocation: "middle",
            nameGap: 28,
            data: gameLabels,
            axisLabel: {
              formatter: function (value) {
                return String(value);
              },
            },
          },
          yAxis: {
            type: "value",
            name: yName,
            min: yMin,
            max: yMax,
            inverse: !!invertY,
            axisLabel: {
              formatter: function (value) {
                return String(Math.round(value * 10) / 10);
              },
            },
          },
          series: [
            {
              name: playerName,
              type: "line",
              data: clamped,
              smooth: false,
              lineStyle: { width: 2, color: colorPlayer },
              itemStyle: { color: colorPlayer },
              markLine: {
                symbol: ["none", "none"],
                silent: true,
                label: { show: false },
                data: markLines,
              },
            },
          ],
        },
        true
      );
      const resizeHandler = () => chart.resize();
      if (container._echartResizeHandler) {
        window.removeEventListener("resize", container._echartResizeHandler);
      }
      window.addEventListener("resize", resizeHandler);
      container._echartResizeHandler = resizeHandler;
    };

    renderLine(
      "tournamentPlayerAvgChart",
      series.avg_series || [],
      "Average",
      150,
      250,
      false,
      series.cut_lines_avg || []
    );
    renderLine(
      "tournamentPlayerPosChart",
      (series.position_series || []).map((v) => Number(v)),
      "Rank",
      1,
      80,
      true,
      series.cut_lines_position || []
    );

    const legendContainer = document.getElementById("tournamentPlayerChartsLegend");
    if (legendContainer) {
      const colorPlayer =
        (window.ColorUtils && typeof window.ColorUtils.getThemeColor === "function" && window.ColorUtils.getThemeColor("primary")) ||
        "#1f77b4";
      const colorRoundBoundary =
        (window.ColorUtils && typeof window.ColorUtils.getThemeColor === "function" && window.ColorUtils.getThemeColor("border")) ||
        "rgba(0,0,0,0.25)";
      const colorCutQualifying =
        (typeof getSemanticColor === "function" && getSemanticColor("negative")) || "#D62728";
      const colorCutRound2 =
        (typeof getSemanticColor === "function" && getSemanticColor("highlight")) || "#ffb000";

      const item = (label, color, dashed = false) => `
        <div class="d-flex align-items-center">
          <span style="display:inline-block;width:26px;height:0;border-top:3px ${dashed ? "dashed" : "solid"} ${color};margin-right:8px;"></span>
          <span>${label}</span>
        </div>
      `;
      legendContainer.innerHTML = [
        item(playerName, colorPlayer, false),
        item("Round Boundary", colorRoundBoundary, false),
        item("Cut Qualifying", colorCutQualifying, true),
        item("Cut Round 2", colorCutRound2, true),
      ].join("");
    }
  }

  async function onPlayerChanged() {
    const season = document.getElementById("tournamentSeason").value.trim();
    const tournament = document.getElementById("tournamentName").value;
    const player = document.getElementById("tournamentPlayerInput").value.trim();
    if (!season || !tournament || !player) {
      setPlayerMode(false);
      renderPlayerSection(null);
      return;
    }
    const exists = tournamentPlayers.some((p) => p.toLowerCase() === player.toLowerCase());
    if (!exists) {
      setPlayerMode(false);
      renderPlayerSection(null);
      return;
    }
    try {
      setPlayerMode(true);
      const payload = await fetchJson(
        `/tournament/get_player_section?season=${encodeURIComponent(season)}&tournament=${encodeURIComponent(tournament)}&player=${encodeURIComponent(player)}`
      );
      renderPlayerSection(payload);
    } catch (err) {
      console.error("Failed to load player section:", err);
      setPlayerMode(false);
      renderPlayerSection(null);
    }
  }

  async function loadTournaments(season) {
    const select = document.getElementById("tournamentName");
    try {
      const data = await fetchJson(`/tournament/get_available_tournaments?season=${encodeURIComponent(season)}`);
      if (!Array.isArray(data) || data.length === 0) {
        select.innerHTML = '<option value="">No tournaments found</option>';
        return;
      }
      select.innerHTML = data
        .map((name) => `<option value="${name}">${name}</option>`)
        .join("");
    } catch (err) {
      console.error("Failed to load tournaments:", err);
      select.innerHTML = '<option value="">Error loading tournaments</option>';
    }
  }

  async function loadRounds(season, tournament) {
    const select = document.getElementById("tournamentRound");
    if (!tournament) {
      select.innerHTML = '<option value="">All / latest</option>';
      return;
    }
    const rounds = await fetchJson(
      `/tournament/get_available_rounds?season=${encodeURIComponent(season)}&tournament=${encodeURIComponent(tournament)}`
    );
    select.innerHTML = ['<option value="">All / latest</option>']
      .concat(
        rounds.map(
          (r) => `<option value="${r.round_number}">${r.round_number} - ${r.round_name || "Round"}</option>`
        )
      )
      .join("");
  }

  async function renderSection() {
    const season = document.getElementById("tournamentSeason").value.trim();
    const tournament = document.getElementById("tournamentName").value;
    const round = document.getElementById("tournamentRound").value;
    if (!season || !tournament) return;

    const roundParam = round ? `&round=${encodeURIComponent(round)}` : "";
    const section = await fetchJson(
      `/tournament/get_section?season=${encodeURIComponent(season)}&tournament=${encodeURIComponent(tournament)}${roundParam}&n=5`
    );
    renderCards(section.cards || []);
    renderBestEfforts(section.best_efforts);
    renderTable("tournamentLeaderboardTable", section.leaderboard);
    renderTable("tournamentRoundResultsTable", section.round_results);
  }

  async function init() {
    const seasonInput = document.getElementById("tournamentSeason");
    const tournamentSelect = document.getElementById("tournamentName");
    const roundSelect = document.getElementById("tournamentRound");

    const params = new URLSearchParams(window.location.search);
    if (params.get("season")) seasonInput.value = params.get("season");

    await loadTournaments(seasonInput.value.trim());
    if (params.get("tournament")) {
      tournamentSelect.value = params.get("tournament");
    }
    await loadRounds(seasonInput.value.trim(), tournamentSelect.value);
    await loadPlayers(seasonInput.value.trim(), tournamentSelect.value);
    if (params.get("round")) {
      roundSelect.value = params.get("round");
    }
    await renderSection();
    setPlayerMode(false);

    seasonInput.addEventListener("change", async () => {
      await loadTournaments(seasonInput.value.trim());
      await loadRounds(seasonInput.value.trim(), tournamentSelect.value);
      await loadPlayers(seasonInput.value.trim(), tournamentSelect.value);
      await renderSection();
      setPlayerMode(false);
    });
    tournamentSelect.addEventListener("change", async () => {
      await loadRounds(seasonInput.value.trim(), tournamentSelect.value);
      await loadPlayers(seasonInput.value.trim(), tournamentSelect.value);
      await renderSection();
      setPlayerMode(false);
    });
    roundSelect.addEventListener("change", async () => {
      await renderSection();
      setPlayerMode(false);
      renderPlayerSection(null);
      const input = document.getElementById("tournamentPlayerInput");
      if (input) input.value = "";
    });
    document.getElementById("tournamentPlayerInput")?.addEventListener("change", onPlayerChanged);
    document.getElementById("tournamentPlayerInput")?.addEventListener("blur", onPlayerChanged);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
