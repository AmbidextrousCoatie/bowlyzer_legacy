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
      container.innerHTML = '<div class="alert alert-info">No summary cards available.</div>';
      return;
    }
    const tournamentCard = cards.find((c) => String(c.title || "").toLowerCase() === "tournament");
    const currentRoundCard = cards.find((c) => String(c.title || "").toLowerCase() === "current round");
    const titleText = tournamentCard
      ? `${tournamentCard.value ?? "Tournament"}${tournamentCard.subtitle ? ` - ${tournamentCard.subtitle}` : ""}`
      : "Tournament Overview";
    const roundText = currentRoundCard
      ? `${currentRoundCard.value ?? ""}${currentRoundCard.subtitle ? ` (${currentRoundCard.subtitle})` : ""}`
      : "";
    const headerText = roundText ? `${titleText} - ${roundText}` : titleText;
    const innerCards = cards.filter((c) => c !== tournamentCard && c !== currentRoundCard);

    container.innerHTML = `
      <div class="card mb-4">
        <div class="card-header">
          <h5 class="mb-0">${headerText}</h5>
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

    // Highlight winner card using rainbow palette green ("3" shade).
    innerCards.forEach((card, idx) => {
      const title = String(card.title || "").toLowerCase();
      if (!title.includes("leader") && !title.includes("winner")) return;
      const el = document.getElementById(`tournamentOverviewStatCard_${idx}`);
      if (!el) return;
      const winnerColor =
        (window.ColorUtils && typeof window.ColorUtils.getPaletteColor === "function" && window.ColorUtils.getPaletteColor(2)) ||
        "#8CBF8A";
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

  function enablePlayerCellNavigation(containerId) {
    const container = document.getElementById(containerId);
    if (!container || container.dataset.playerCellNavBound === "1") return;
    container.dataset.playerCellNavBound = "1";
    container.addEventListener("click", async (event) => {
      const cell = event.target.closest(".tabulator-cell");
      if (!cell) return;
      const field = String(cell.getAttribute("tabulator-field") || "").toLowerCase();
      if (field !== "player") return;
      const playerName = String(cell.textContent || "").trim();
      if (!playerName) return;
      const input = document.getElementById("tournamentPlayerInput");
      if (!input) return;
      input.value = playerName;
      await onPlayerChanged();
    });
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
  let playerCutLineMode = "dynamic"; // "dynamic" or "horizontal"
  const playerComboCache = new Map();
  const currentFilters = {
    season: "",
    tournament: "",
    round: "",
  };

  function syncUrlWithFilters() {
    const params = new URLSearchParams(window.location.search);
    if (currentFilters.season) params.set("season", currentFilters.season);
    else params.delete("season");
    if (currentFilters.tournament) params.set("tournament", currentFilters.tournament);
    else params.delete("tournament");
    if (currentFilters.round) params.set("round", currentFilters.round);
    else params.delete("round");
    const url = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState({}, "", url);
  }

  function renderButtonGroup(containerId, items, activeValue, onSelect) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!Array.isArray(items) || items.length === 0) {
      container.innerHTML = '<span class="text-muted">No options</span>';
      return;
    }
    container.innerHTML = items
      .map((item) => {
        const value = String(item.value ?? "");
        const label = String(item.label ?? value);
        const active = value === String(activeValue ?? "");
        return `
          <button type="button" class="btn btn-sm ${active ? "btn-primary" : "btn-outline-primary"} me-2 mb-2" data-value="${value}">
            ${label}
          </button>
        `;
      })
      .join("");
    container.querySelectorAll("button[data-value]").forEach((btn) => {
      btn.addEventListener("click", () => onSelect(btn.getAttribute("data-value") || ""));
    });
  }
  function setPlayerMode(enabled) {
    const ids = ["tournamentCards", "tournamentBestEfforts", "tournamentLeaderboardCard", "tournamentRoundResultsCard"];
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.style.display = enabled ? "none" : "";
    });
    const roundFilter = document.getElementById("tournamentRoundFilterGroup");
    if (roundFilter) roundFilter.style.display = enabled ? "none" : "";
  }

  function getSelectedPlayer() {
    const input = document.getElementById("tournamentPlayerInput");
    return (input?.value || "").trim();
  }

  async function comboHasPlayer(season, tournament, player) {
    if (!season || !tournament || !player) return false;
    const key = `${season}||${tournament}||${player.toLowerCase()}`;
    if (playerComboCache.has(key)) return playerComboCache.get(key);
    try {
      const players = await fetchJson(
        `/tournament/get_available_players?season=${encodeURIComponent(season)}&tournament=${encodeURIComponent(tournament)}`
      );
      const found = Array.isArray(players) && players.some((p) => String(p).toLowerCase() === player.toLowerCase());
      playerComboCache.set(key, found);
      return found;
    } catch (err) {
      console.warn("comboHasPlayer lookup failed:", err);
      playerComboCache.set(key, false);
      return false;
    }
  }

  async function loadPlayers(season, tournament, round, preservePlayer = false) {
    const list = document.getElementById("tournamentPlayersList");
    const input = document.getElementById("tournamentPlayerInput");
    if (!list || !input || !tournament) return;
    const previousValue = input.value.trim();
    try {
      const roundParam = round ? `&round=${encodeURIComponent(round)}` : "";
      tournamentPlayers = await fetchJson(
        `/tournament/get_available_players?season=${encodeURIComponent(season)}&tournament=${encodeURIComponent(tournament)}${roundParam}`
      );
      list.innerHTML = (tournamentPlayers || [])
        .map((p) => `<option value="${p}"></option>`)
        .join("");
      if (preservePlayer && previousValue) {
        const matched = (tournamentPlayers || []).find((p) => String(p).toLowerCase() === previousValue.toLowerCase());
        input.value = matched || "";
      } else {
        input.value = "";
      }
    } catch (err) {
      console.error("Failed to load players:", err);
      tournamentPlayers = [];
      list.innerHTML = "";
      input.value = "";
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
                  <div class="d-flex justify-content-end mb-2">
                    <div class="btn-group btn-group-sm" role="group" aria-label="Cut line mode">
                      <button type="button" id="tournamentCutModeDynamic" class="btn ${playerCutLineMode === "dynamic" ? "btn-primary" : "btn-outline-primary"}">Dynamic Cut Pace</button>
                      <button type="button" id="tournamentCutModeHorizontal" class="btn ${playerCutLineMode === "horizontal" ? "btn-primary" : "btn-outline-primary"}">Horizontal Cut</button>
                    </div>
                  </div>
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
      const highlight =
        (window.ColorUtils && typeof window.ColorUtils.getPaletteColor === "function" && window.ColorUtils.getPaletteColor(2)) ||
        "#8CBF8A";
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
    renderPlayerProgressCharts(payload.progress_series, payload.player, playerCutLineMode);
    document.getElementById("tournamentCutModeDynamic")?.addEventListener("click", () => {
      playerCutLineMode = "dynamic";
      renderPlayerSection(payload);
    });
    document.getElementById("tournamentCutModeHorizontal")?.addEventListener("click", () => {
      playerCutLineMode = "horizontal";
      renderPlayerSection(payload);
    });
    document.getElementById("tournamentBackToOverviewBtn")?.addEventListener("click", async () => {
      const input = document.getElementById("tournamentPlayerInput");
      if (input) input.value = "";
      setPlayerMode(false);
      renderPlayerSection(null);
      await refreshSeasonButtons();
      await refreshTournamentButtons();
      await refreshRoundButtons();
      await renderSection();
    });
  }

  function renderPlayerProgressCharts(series, playerName, cutLineMode = "dynamic") {
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
    const roundBoundaries = roundEnds.slice(0, -1).map((v) => v + 0.5);

    const renderLine = (containerId, dataSeries, yName, yMin, yMax, invertY, cutLines, extraLines = []) => {
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
      const colorLeader =
        (typeof getSemanticColor === "function" && getSemanticColor("secondary")) || "#6f42c1";
      const maxX = totalGames + 0.5;
      const firstBoundary = roundBoundaries[0] ?? maxX;
      const secondBoundary = roundBoundaries[1] ?? maxX;

      const buildPointSeries = (arr, startX = 0, endX = maxX, extendStart = false, extendEnd = false) => {
        const points = [];
        let firstVal = null;
        let lastVal = null;
        for (let i = 0; i < (arr || []).length; i += 1) {
          const raw = arr[i];
          if (raw === null || raw === undefined || raw === "") continue;
          const n = Number(raw);
          if (!Number.isFinite(n)) continue;
          const x = i + 1;
          if (x < startX || x > endX) continue;
          const y = Math.max(yMin, Math.min(yMax, n));
          points.push([x, y]);
          if (firstVal === null) firstVal = y;
          lastVal = y;
        }
        if (extendStart && firstVal !== null && startX > 0 && startX < 1e9) {
          points.unshift([startX, firstVal]);
        }
        if (extendEnd && lastVal !== null && endX > 0 && endX < 1e9) {
          points.push([endX, lastVal]);
        }
        return points;
      };

      const clamped = buildPointSeries(dataSeries || [], 0, maxX, false, false);

      const dynamicQualifyingRaw =
        series.cut_lines_avg_dynamic && Array.isArray(series.cut_lines_avg_dynamic.qualifying)
          ? series.cut_lines_avg_dynamic.qualifying
          : [];
      const dynamicRound2Raw =
        series.cut_lines_avg_dynamic && Array.isArray(series.cut_lines_avg_dynamic.round2)
          ? series.cut_lines_avg_dynamic.round2
          : [];
      const dynamicQualifying = buildPointSeries(dynamicQualifyingRaw, 0, firstBoundary, false, true);
      const dynamicRound2 = buildPointSeries(dynamicRound2Raw, firstBoundary, secondBoundary, true, true);

      const markLines = [];
      // Vertical round separators
      roundBoundaries.forEach((x) => {
        markLines.push({ xAxis: x, lineStyle: { color: colorRoundBoundary, type: "solid", width: 1 } });
      });
      // Horizontal cut/reference lines (legacy mode option).
      if (cutLineMode === "horizontal") {
        const cutValues = (cutLines || [])
          .map((v) => Number(v))
          .filter((v) => Number.isFinite(v));
        if (cutValues.length > 0) {
          const y = Math.max(yMin, Math.min(yMax, cutValues[0]));
          markLines.push([
            { coord: [0, y], lineStyle: { color: colorCutQualifying, type: "dashed", width: 2 } },
            { coord: [firstBoundary, y] },
          ]);
        }
        if (cutValues.length > 1) {
          const y = Math.max(yMin, Math.min(yMax, cutValues[1]));
          markLines.push([
            { coord: [firstBoundary, y], lineStyle: { color: colorCutRound2, type: "dashed", width: 2 } },
            { coord: [secondBoundary, y] },
          ]);
        }
      }

      const extraCutSeries = [];
      if (cutLineMode === "dynamic" && yName === "Average") {
        extraCutSeries.push(
          {
            name: "Cut Qualifying",
            type: "line",
            data: dynamicQualifying,
            smooth: false,
            connectNulls: false,
            showSymbol: false,
            lineStyle: { width: 2, type: "dashed", color: colorCutQualifying },
            itemStyle: { color: colorCutQualifying },
            z: 1,
          },
          {
            name: "Cut Round 2",
            type: "line",
            data: dynamicRound2,
            smooth: false,
            connectNulls: false,
            showSymbol: false,
            lineStyle: { width: 2, type: "dashed", color: colorCutRound2 },
            itemStyle: { color: colorCutRound2 },
            z: 1,
          }
        );
      }

      const extraOverlaySeries = (extraLines || []).map((line) => {
        const mapped = buildPointSeries(line?.data || [], 0, maxX, false, false);
        return {
          name: line.name || "Reference",
          type: "line",
          data: mapped,
          smooth: false,
          connectNulls: false,
          showSymbol: false,
          lineStyle: {
            width: line.width || 2,
            type: line.dashed ? "dashed" : "solid",
            color: line.color || colorLeader,
          },
          itemStyle: { color: line.color || colorLeader },
          z: 1,
        };
      });

      chart.setOption(
        {
          animation: false,
          tooltip: { trigger: "axis" },
          legend: { show: false },
          grid: { top: "10%", right: "5%", bottom: "14%", left: "10%", containLabel: true },
          xAxis: {
            type: "value",
            name: "Game",
            nameLocation: "middle",
            nameGap: 28,
            min: 0,
            max: maxX,
            interval: 1,
            axisLabel: {
              formatter: function (value) {
                if (!Number.isFinite(value)) return "";
                return Number.isInteger(value) && value >= 1 && value <= totalGames ? String(value) : "";
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
              z: 2,
            },
            ...extraCutSeries,
            ...extraOverlaySeries,
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
      series.cut_lines_avg || [],
      [
        {
          name: "Tournament Leader",
          data: series.tournament_leader_avg_series || [],
          dashed: true,
          color:
            (typeof getSemanticColor === "function" && getSemanticColor("secondary")) || "#6f42c1",
          width: 2,
        },
      ]
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
      const colorLeader =
        (typeof getSemanticColor === "function" && getSemanticColor("secondary")) || "#6f42c1";

      const item = (label, color, dashed = false) => `
        <div class="d-flex align-items-center">
          <span style="display:inline-block;width:26px;height:0;border-top:3px ${dashed ? "dashed" : "solid"} ${color};margin-right:8px;"></span>
          <span>${label}</span>
        </div>
      `;
      legendContainer.innerHTML = [
        item(playerName, colorPlayer, false),
        item("Tournament Leader", colorLeader, true),
        item("Round Boundary", colorRoundBoundary, false),
        item(cutLineMode === "dynamic" ? "Cut Qualifying (pace)" : "Cut Qualifying", colorCutQualifying, true),
        item(cutLineMode === "dynamic" ? "Cut Round 2 (pace)" : "Cut Round 2", colorCutRound2, true),
      ].join("");
    }
  }

  async function onPlayerChanged() {
    const season = currentFilters.season;
    const tournament = currentFilters.tournament;
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
      await refreshSeasonButtons();
      await refreshTournamentButtons();
      await refreshRoundButtons();
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

  async function getAvailableSeasons(tournament) {
    try {
      const tournamentParam = tournament ? `?tournament=${encodeURIComponent(tournament)}` : "";
      const data = await fetchJson(`/tournament/get_available_seasons${tournamentParam}`);
      return Array.isArray(data) ? data : [];
    } catch (err) {
      console.error("Failed to load seasons:", err);
      return [];
    }
  }

  async function getAvailableTournaments(season) {
    try {
      const data = await fetchJson(`/tournament/get_available_tournaments?season=${encodeURIComponent(season)}`);
      return Array.isArray(data) ? data : [];
    } catch (err) {
      console.error("Failed to load tournaments:", err);
      return [];
    }
  }

  async function getAvailableRounds(season, tournament) {
    if (!season || !tournament) return [];
    try {
      const rounds = await fetchJson(
        `/tournament/get_available_rounds?season=${encodeURIComponent(season)}&tournament=${encodeURIComponent(tournament)}`
      );
      return Array.isArray(rounds) ? rounds : [];
    } catch (err) {
      console.error("Failed to load rounds:", err);
      return [];
    }
  }

  function pickValue(items, preferred) {
    if (!Array.isArray(items) || items.length === 0) return "";
    const normalizedPreferred = preferred == null ? "" : String(preferred);
    const match = items.find((item) => String(item.value ?? item) === normalizedPreferred);
    if (match) return String(match.value ?? match);
    return String(items[0].value ?? items[0]);
  }

  async function renderSection() {
    const season = currentFilters.season;
    const tournament = currentFilters.tournament;
    const round = currentFilters.round;
    if (!season || !tournament) return;

    const roundParam = round ? `&round=${encodeURIComponent(round)}` : "";
    const section = await fetchJson(
      `/tournament/get_section?season=${encodeURIComponent(season)}&tournament=${encodeURIComponent(tournament)}${roundParam}&n=5`
    );
    renderCards(section.cards || []);
    renderBestEfforts(section.best_efforts);
    renderTable("tournamentLeaderboardTable", section.leaderboard);
    renderTable("tournamentRoundResultsTable", section.round_results);
    enablePlayerCellNavigation("tournamentLeaderboardTable");
    enablePlayerCellNavigation("tournamentRoundResultsTable");
  }

  async function applyFiltersAndRender(preservePlayer = false) {
    const playerBefore = getSelectedPlayer();
    await loadPlayers(currentFilters.season, currentFilters.tournament, currentFilters.round, preservePlayer);
    await renderSection();
    syncUrlWithFilters();
    const playerAfter = getSelectedPlayer();
    const stillValidPlayer =
      preservePlayer &&
      !!playerAfter &&
      (tournamentPlayers || []).some((p) => String(p).toLowerCase() === playerAfter.toLowerCase());
    if (stillValidPlayer) {
      setPlayerMode(true);
      try {
        const payload = await fetchJson(
          `/tournament/get_player_section?season=${encodeURIComponent(currentFilters.season)}&tournament=${encodeURIComponent(
            currentFilters.tournament
          )}&player=${encodeURIComponent(playerAfter)}`
        );
        renderPlayerSection(payload);
      } catch (err) {
        console.error("Failed to refresh player section:", err);
        setPlayerMode(false);
        renderPlayerSection(null);
      }
    } else {
      if (preservePlayer && playerBefore && !playerAfter) {
        renderPlayerSection(null);
      }
      setPlayerMode(false);
      renderPlayerSection(null);
    }
  }

  async function refreshRoundButtons() {
    const rounds = await getAvailableRounds(currentFilters.season, currentFilters.tournament);
    const roundItems = [{ value: "", label: "All / latest" }].concat(
      rounds.map((r) => ({
        value: String(r.round_number),
        label: `${r.round_number} - ${r.round_name || "Round"}`,
      }))
    );
    const preferredRound = currentFilters.round;
    currentFilters.round = pickValue(roundItems, currentFilters.round);
    renderButtonGroup("tournamentRoundButtons", roundItems, currentFilters.round, async (value) => {
      currentFilters.round = value || "";
      await applyFiltersAndRender(true);
      await refreshRoundButtons();
    });
    return preferredRound === currentFilters.round;
  }

  async function refreshTournamentButtons() {
    const tournaments = await getAvailableTournaments(currentFilters.season);
    let tournamentItems = tournaments.map((name) => ({ value: name, label: name }));
    const selectedPlayer = getSelectedPlayer();
    if (selectedPlayer) {
      const checks = await Promise.all(
        tournamentItems.map(async (item) => ({
          item,
          ok: await comboHasPlayer(currentFilters.season, item.value, selectedPlayer),
        }))
      );
      const filtered = checks.filter((x) => x.ok).map((x) => x.item);
      if (filtered.length > 0) tournamentItems = filtered;
    }
    const preferredTournament = currentFilters.tournament;
    currentFilters.tournament = pickValue(tournamentItems, currentFilters.tournament);
    renderButtonGroup("tournamentNameButtons", tournamentItems, currentFilters.tournament, async (value) => {
      currentFilters.tournament = value || "";
      await refreshTournamentButtons();
      await refreshRoundButtons();
      await applyFiltersAndRender(true);
    });
    return preferredTournament === currentFilters.tournament;
  }

  async function refreshSeasonButtons() {
    const seasons = await getAvailableSeasons(currentFilters.tournament);
    let seasonItems = seasons.map((s) => ({ value: String(s), label: String(s) }));
    const selectedPlayer = getSelectedPlayer();
    if (selectedPlayer && currentFilters.tournament) {
      const checks = await Promise.all(
        seasonItems.map(async (item) => ({
          item,
          ok: await comboHasPlayer(item.value, currentFilters.tournament, selectedPlayer),
        }))
      );
      const filtered = checks.filter((x) => x.ok).map((x) => x.item);
      if (filtered.length > 0) seasonItems = filtered;
    }
    currentFilters.season = pickValue(seasonItems, currentFilters.season);
    renderButtonGroup("tournamentSeasonButtons", seasonItems, currentFilters.season, async (value) => {
      currentFilters.season = value || "";
      await refreshSeasonButtons();
      const keptTournament = await refreshTournamentButtons();
      if (!keptTournament) {
        // Keep current reset behavior when the new season/tournament combo is invalid.
        currentFilters.round = "";
      }
      await refreshRoundButtons();
      await applyFiltersAndRender(true);
    });
  }

  async function init() {
    const params = new URLSearchParams(window.location.search);
    const seasons = await getAvailableSeasons();
    const seasonItems = seasons.map((s) => ({ value: String(s), label: String(s) }));
    currentFilters.season = pickValue(seasonItems, params.get("season"));

    await refreshSeasonButtons();

    currentFilters.tournament = params.get("tournament") || "";
    await refreshTournamentButtons();

    currentFilters.round = params.get("round") || "";
    await refreshRoundButtons();

    await applyFiltersAndRender(true);

    document.getElementById("tournamentPlayerInput")?.addEventListener("change", onPlayerChanged);
    document.getElementById("tournamentPlayerInput")?.addEventListener("blur", onPlayerChanged);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
