(function () {
  function tt(key, fallback) {
    if (typeof t === "function") return t(key, fallback);
    return fallback || key;
  }

  function localizeTournamentCardTitle(rawTitle) {
    const title = String(rawTitle || "").trim();
    const map = {
      Tournament: () => tt("ui.tournament.card.tournament", "Tournament"),
      "Current Round": () => tt("ui.tournament.card.current_round", "Current Round"),
      "Cut Line": () => tt("ui.tournament.card.cut_line", "Cut Line"),
      "Tournament Leader": () => tt("ui.tournament.card.tournament_leader", "Tournament Leader"),
      Participants: () => tt("ui.tournament.card.participants", "Participants"),
      "Stage Winner": () => tt("ui.tournament.card.stage_winner", "Stage Winner"),
    };
    return map[title] ? map[title]() : title;
  }

  function localizeTournamentCardSubtitle(rawSubtitle) {
    const subtitle = String(rawSubtitle || "").trim();
    if (subtitle === "Field size") {
      return tt("ui.tournament.card.field_size", "Field size");
    }
    return subtitle;
  }

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

  function refreshTournamentUiText() {
    const playerInput = document.getElementById("tournamentPlayerInput");
    if (playerInput) {
      playerInput.placeholder = tt("ui.tournament.player_placeholder", "Type to filter players...");
    }
    renderRoundResultsHeatmapControls();
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
      container.innerHTML = `<div class="alert alert-info">${tt("ui.tournament.no_summary_cards", "No summary cards available.")}</div>`;
      return;
    }
    const tournamentCard = cards.find((c) => String(c.title || "").toLowerCase() === "tournament");
    const currentRoundCard = cards.find((c) => String(c.title || "").toLowerCase() === "current round");
    const titleText = tournamentCard
      ? `${tournamentCard.value ?? tt("ui.tournament.tournament", "Tournament")}${tournamentCard.subtitle ? ` - ${tournamentCard.subtitle}` : ""}`
      : tt("ui.tournament.overview", "Tournament Overview");
    const roundText = currentRoundCard
      ? `${currentRoundCard.value ?? ""}`
      : "";
    const headerText = roundText ? `${titleText} - ${roundText}` : titleText;
    const innerCards = cards.filter((c) => c !== tournamentCard && c !== currentRoundCard);

    const isPlayerCard = (card) => {
      const title = String(card?.title || "").toLowerCase();
      const value = String(card?.value ?? "").trim();
      if (!value) return false;
      if (["n/a", "-", "unknown"].includes(value.toLowerCase())) return false;
      return title.includes("leader") || title.includes("winner") || title.includes("cut line");
    };

    const renderCardValue = (card) => {
      const value = card?.value ?? "";
      if (!isPlayerCard(card)) return String(value);
      return `<a href="#" class="tournament-player-link" data-player-name="${String(value).replace(/"/g, "&quot;")}">${String(value)}</a>`;
    };

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
                    <div class="card-header"><h6 class="mb-0">${localizeTournamentCardTitle(card.title || "")}</h6></div>
                    <div class="card-body">
                      <div class="h5 mb-1">${renderCardValue(card)}</div>
                      <small class="text-muted">${localizeTournamentCardSubtitle(card.subtitle || "")}</small>
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

    container.querySelectorAll(".tournament-player-link").forEach((el) => {
      el.addEventListener("click", async (evt) => {
        evt.preventDefault();
        const playerName = String(el.getAttribute("data-player-name") || "").trim();
        if (!playerName) return;
        const input = document.getElementById("tournamentPlayerInput");
        if (!input) return;
        input.value = playerName;
        await onPlayerChanged();
      });
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
    container.innerHTML = `<div class="alert alert-warning">${tt("ui.tournament.tabulator_unavailable", "Tabulator renderer unavailable.")}</div>`;
  }

  function updateRoundResultsHeader(section) {
    const headerEl = document.querySelector("#tournamentRoundResultsCard .card-header h5");
    if (!headerEl) return;
    const roundValue = String(currentFilters.round || "").trim();
    if (!roundValue) {
      headerEl.textContent = tt("ui.tournament.round_results", "Round Results");
      return;
    }
    const rounds = Array.isArray(section?.rounds) ? section.rounds : [];
    const selected = rounds.find((r) => String(r?.round_number ?? "") === roundValue);
    const stageName = selected?.round_name ? String(selected.round_name).trim() : `${tt("ui.tournament.round", "Round")} ${roundValue}`;
    headerEl.textContent = `${tt("ui.tournament.round_results", "Round Results")} - ${stageName}`;
  }

  const DEFAULT_GAME_HEATMAP_RANGE = {
    min: 130,
    max: 270,
    high_band_min: 271,
    high_band_max: 299,
    perfect_score: 300,
  };

  function renderRoundResultsHeatmapControls(containerId = "tournamentRoundResultsHeatmapControls") {
    const wrap = document.getElementById(containerId);
    if (!wrap) return;
    const buttonId = `${containerId}Toggle`;
    wrap.innerHTML = `
      <div class="d-flex align-items-center">
        <span class="me-2 fw-semibold">${tt("ui.tournament.heatmap", "Heatmap")}</span>
        <button type="button" id="${buttonId}" class="btn btn-sm ${roundResultsHeatmapEnabled ? "btn-primary" : "btn-outline-primary"}">
          ${roundResultsHeatmapEnabled ? tt("ui.common.on", "On") : tt("ui.common.off", "Off")}
        </button>
      </div>
    `;
    const btn = document.getElementById(buttonId);
    if (!btn) return;
    btn.addEventListener("click", () => {
      roundResultsHeatmapEnabled = !roundResultsHeatmapEnabled;
      renderRoundResultsHeatmapControls("tournamentRoundResultsHeatmapControls");
      renderRoundResultsHeatmapControls("tournamentPlayerRoundResultsHeatmapControls");
      applyRoundResultsHeatmapToTable("tournamentRoundResultsTable", currentRoundResultsHeatmapRange);
      applyRoundResultsHeatmapToTable("tournamentPlayerRoundTable", currentPlayerRoundHeatmapRange);
    });
  }

  function applyRoundResultsHeatmapToTable(containerId = "tournamentRoundResultsTable", rangeOverride = null) {
    const table = document.getElementById(containerId);
    if (!table) return false;
    const gameCells = table.querySelectorAll(".tabulator-cell[tabulator-field^='game_']");
    if (!gameCells.length) return false;
    gameCells.forEach((cell) => {
      cell.style.removeProperty("background-color");
      cell.style.removeProperty("font-weight");
      cell.style.removeProperty("color");
      cell.style.removeProperty("box-shadow");

      if (!roundResultsHeatmapEnabled) return;
      const raw = String(cell.textContent || "").trim();
      if (!raw) return;
      const value = parseFloat(raw);
      if (!Number.isFinite(value)) return;

      const range = rangeOverride || DEFAULT_GAME_HEATMAP_RANGE;
      const min = Number(range.min ?? DEFAULT_GAME_HEATMAP_RANGE.min);
      const max = Number(range.max ?? DEFAULT_GAME_HEATMAP_RANGE.max);
      const highBandMin = Number(range.high_band_min ?? DEFAULT_GAME_HEATMAP_RANGE.high_band_min);
      const highBandMax = Number(range.high_band_max ?? DEFAULT_GAME_HEATMAP_RANGE.high_band_max);
      const perfectScore = Number(range.perfect_score ?? DEFAULT_GAME_HEATMAP_RANGE.perfect_score);

      if (value === perfectScore) {
        const perfectColor = window.ColorUtils?.getThemeColor("heatMapPerfect") || "#ffc107";
        const perfectBorder = window.ColorUtils?.getThemeColor("heatMapPerfectBorder") || "#b77900";
        cell.style.setProperty("background-color", perfectColor, "important");
        cell.style.setProperty("font-weight", "800", "important");
        cell.style.setProperty("color", "#111827", "important");
        cell.style.setProperty("box-shadow", `inset 0 0 0 2px ${perfectBorder}`, "important");
        return;
      }

      if (value >= highBandMin && value <= highBandMax) {
        const highBandColor = window.ColorUtils?.getThemeColor("heatMapHighBand") || "#ffe7a3";
        cell.style.setProperty("background-color", highBandColor, "important");
        cell.style.setProperty("font-weight", "600", "important");
        cell.style.setProperty("color", "#1f2933", "important");
        return;
      }

      if (typeof window.ColorUtils?.getHeatMapColor === "function") {
        const color = window.ColorUtils.getHeatMapColor(value, min, max);
        cell.style.setProperty("background-color", color, "important");
        cell.style.setProperty("color", "#1f2933", "important");
      }
    });
    return true;
  }

  function scheduleRoundResultsHeatmapApply(maxAttempts = 40, delayMs = 120) {
    let attempts = 0;
    const tick = () => {
      attempts += 1;
      const okOverview = applyRoundResultsHeatmapToTable("tournamentRoundResultsTable", currentRoundResultsHeatmapRange);
      const okPlayer = applyRoundResultsHeatmapToTable("tournamentPlayerRoundTable", currentPlayerRoundHeatmapRange);
      const ok = okOverview || okPlayer;
      if (ok || attempts >= maxAttempts) return;
      window.setTimeout(tick, delayMs);
    };
    tick();
  }

  function updateLeaderboardHeader(section) {
    const headerEl = document.querySelector("#tournamentLeaderboardCard .card-header h5");
    if (!headerEl) return;
    const roundValue = String(currentFilters.round || "").trim();
    if (!roundValue) {
      headerEl.textContent = tt("ui.tournament.leaderboard", "Leaderboard");
      return;
    }
    const rounds = Array.isArray(section?.rounds) ? section.rounds : [];
    const selected = rounds.find((r) => String(r?.round_number ?? "") === roundValue);
    const stageName = selected?.round_name ? String(selected.round_name).trim() : `${tt("ui.tournament.round", "Round")} ${roundValue}`;
    headerEl.textContent = `${tt("ui.tournament.leaderboard", "Leaderboard")} - ${stageName}`;
  }

  function setRoundResultsVisibility() {
    const card = document.getElementById("tournamentRoundResultsCard");
    if (!card) return;
    const roundValue = String(currentFilters.round || "").trim();
    card.style.display = roundValue ? "" : "none";
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
      return `<div class="text-muted">${tt("ui.tournament.no_entries", "No entries")}</div>`;
    }
    return items
      .map(
        (entry) => `
          <div class="d-flex justify-content-between">
            <span>${entry.player || tt("ui.tournament.unknown", "Unknown")}${entry.club ? ` (${compactClubName(entry.club)})` : ""}</span>
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
          <h5>${tt("ui.tournament.best_efforts_top_n", "Best Efforts (Top {n})").replace("{n}", String(n))}</h5>
        </div>
        <div class="card-body">
          <div class="row g-3">
            ${sections
              .map(
                (section) => `
                <div class="col-lg-6">
                  <div class="card h-100">
                    <div class="card-header">
                      <h6>${section.scope || tt("ui.tournament.scope", "Scope")}</h6>
                    </div>
                    <div class="card-body">
                      <div class="mb-3">
                        <h6 class="text-muted">${tt("ui.tournament.best_games", "Best Games")}</h6>
                        ${renderEffortRows(section.best_games)}
                      </div>
                      <div class="mb-3">
                        <h6 class="text-muted">${tt("ui.tournament.best_pairs", "Best Pairs")}</h6>
                        ${renderEffortRows(section.best_pairs)}
                      </div>
                      <div>
                        <h6 class="text-muted">${tt("ui.tournament.best_blocks", "Best Blocks")}</h6>
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
  let roundResultsHeatmapEnabled = false;
  let currentRoundResultsHeatmapRange = DEFAULT_GAME_HEATMAP_RANGE;
  let currentPlayerRoundHeatmapRange = DEFAULT_GAME_HEATMAP_RANGE;
  const playerComboCache = new Map();
  const currentFilters = {
    season: "",
    tournament: "",
    round: "",
  };

  function normalizePlayerTokens(name) {
    return String(name || "")
      .trim()
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean);
  }

  function resolvePlayerName(rawName, availablePlayers) {
    const target = String(rawName || "").trim();
    if (!target) return "";
    const players = Array.isArray(availablePlayers) ? availablePlayers : [];
    const exact = players.find((p) => String(p).toLowerCase() === target.toLowerCase());
    if (exact) return exact;

    const targetTokens = normalizePlayerTokens(target);
    if (targetTokens.length === 2) {
      const reversed = `${targetTokens[1]} ${targetTokens[0]}`;
      const revMatch = players.find((p) => String(p).toLowerCase() === reversed);
      if (revMatch) return revMatch;
    }
    // Fallback: token-set equality (handles common first/last inversion).
    const targetKey = targetTokens.slice().sort().join("|");
    if (!targetKey) return "";
    const tokenMatch = players.find((p) => normalizePlayerTokens(p).slice().sort().join("|") === targetKey);
    return tokenMatch || "";
  }

  function syncUrlWithFilters() {
    const params = new URLSearchParams(window.location.search);
    if (currentFilters.season) params.set("season", currentFilters.season);
    else params.delete("season");
    if (currentFilters.tournament) params.set("tournament", currentFilters.tournament);
    else params.delete("tournament");
    if (currentFilters.round) params.set("round", currentFilters.round);
    else params.delete("round");
    const selectedPlayer = getSelectedPlayer();
    if (selectedPlayer) params.set("player", selectedPlayer);
    else params.delete("player");
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
            <button id="tournamentBackToOverviewBtn" class="btn btn-sm btn-primary">${tt("ui.tournament.back_to_overview", "Back to Tournament Overview")}</button>
          </div>
        </div>
        <div class="card-body">
          <div class="row g-3 mb-3">
            <div class="col-md-4">
              <div class="card h-100" id="tournamentFinalPositionCard">
                <div class="card-header"><h6>${tt("ui.tournament.final_position", "Final Position")}</h6></div>
                <div class="card-body">
                  <div class="h5 mb-1">${payload.summary?.final_position ?? "-"}</div>
                  <small class="text-muted">${tt("ui.tournament.after_final_game", "After final game")}</small>
                </div>
              </div>
            </div>
            <div class="col-md-4">
              <div class="card h-100">
                <div class="card-header"><h6>${tt("ui.tournament.average", "Average")}</h6></div>
                <div class="card-body">
                  <div class="h5 mb-1">${payload.summary?.average ?? "-"}</div>
                  <small class="text-muted">${tt("ui.tournament.cumulated", "Cumulated")}</small>
                </div>
              </div>
            </div>
            <div class="col-md-4">
              <div class="card h-100">
                <div class="card-header"><h6>${tt("ui.tournament.best_position", "Best Position")}</h6></div>
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
                <div class="card-header"><h6>${tt("ui.tournament.highest_game", "Highest Game")}</h6></div>
                <div class="card-body">
                  <div class="h5 mb-1">${payload.best_efforts?.highest_game?.score ?? "-"}</div>
                  <small class="text-muted">${payload.best_efforts?.highest_game?.stage || ""} ${payload.best_efforts?.highest_game?.game ? `(G${payload.best_efforts.highest_game.game})` : ""}</small>
                </div>
              </div>
            </div>
            <div class="col-md-4">
              <div class="card h-100">
                <div class="card-header"><h6>${tt("ui.tournament.highest_pair", "Highest Pair")}</h6></div>
                <div class="card-body">
                  <div class="h5 mb-1">${payload.best_efforts?.highest_pair?.score ?? "-"}</div>
                  <small class="text-muted">${payload.best_efforts?.highest_pair?.stage || ""} ${payload.best_efforts?.highest_pair?.pair ? `(${payload.best_efforts.highest_pair.pair})` : ""}</small>
                </div>
              </div>
            </div>
            <div class="col-md-4">
              <div class="card h-100">
                <div class="card-header"><h6>${tt("ui.tournament.highest_block", "Highest Block")}</h6></div>
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
                <div class="card-header d-flex justify-content-between align-items-center">
                  <h6 class="mb-0">${tt("ui.tournament.cum_avg_over_games", "Cumulated Average Over Games")}</h6>
                  <div class="d-flex align-items-center">
                    <span class="me-2 fw-semibold">${tt("ui.tournament.cut", "Cut")}</span>
                    <button type="button" id="tournamentCutModeToggle" class="btn btn-sm btn-primary">
                      ${playerCutLineMode === "dynamic" ? tt("ui.tournament.dynamic", "Dynamic") : tt("ui.tournament.static", "Static")}
                    </button>
                  </div>
                </div>
                <div class="card-body">
                  <div id="tournamentPlayerAvgChart" style="width:100%; min-width:100%; height:280px;"></div>
                </div>
              </div>
            </div>
            <div class="col-md-6">
              <div class="card h-100">
                <div class="card-header"><h6>${tt("ui.tournament.cum_pos_over_games", "Cumulated Position Over Games")}</h6></div>
                <div class="card-body">
                  <div id="tournamentPlayerPosChart" style="width:100%; min-width:100%; height:280px;"></div>
                </div>
              </div>
            </div>
          </div>
          <div class="d-flex justify-content-center mb-3">
            <div id="tournamentPlayerChartsLegend" class="d-flex flex-wrap justify-content-center gap-3"></div>
          </div>
          <div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
              <h6 class="mb-0">${tt("ui.tournament.results", "Results")}</h6>
              <div id="tournamentPlayerRoundResultsHeatmapControls"></div>
            </div>
            <div class="card-body">
              <div id="tournamentPlayerRoundTable"></div>
            </div>
          </div>
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
    renderRoundResultsHeatmapControls("tournamentPlayerRoundResultsHeatmapControls");
    currentPlayerRoundHeatmapRange =
      payload?.round_table?.metadata?.heatmap_ranges?.game_score || DEFAULT_GAME_HEATMAP_RANGE;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => scheduleRoundResultsHeatmapApply());
    });
    renderPlayerProgressCharts(payload.progress_series, payload.player, playerCutLineMode);
    document.getElementById("tournamentCutModeToggle")?.addEventListener("click", () => {
      playerCutLineMode = playerCutLineMode === "dynamic" ? "horizontal" : "dynamic";
      renderPlayerSection(payload);
    });
    document.getElementById("tournamentBackToOverviewBtn")?.addEventListener("click", async () => {
      const input = document.getElementById("tournamentPlayerInput");
      if (input) input.value = "";
      setPlayerMode(false);
      renderPlayerSection(null);
      syncUrlWithFilters();
      await refreshSeasonButtons();
      await refreshTournamentButtons();
      await refreshRoundButtons();
      await renderSection();
    });
  }

  function renderPlayerProgressCharts(series, playerName, cutLineMode = "dynamic") {
    if (!series || !Array.isArray(series.labels) || series.labels.length === 0) return;
    if (typeof echarts === "undefined") {
      console.warn(tt("ui.tournament.echarts_unavailable", "echarts unavailable; player charts cannot render."));
      return;
    }
    const totalGames = series.labels.length;
    const gameLabels = Array.from({ length: totalGames }, (_, i) => i + 1);
    const colorCutUnified =
      (typeof getSemanticColor === "function" && getSemanticColor("negative")) || "#D62728";
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

      const collectNumericValues = (arr) =>
        (Array.isArray(arr) ? arr : [])
          .map((v) => Number(v))
          .filter((v) => Number.isFinite(v));

      // Auto-scale average chart so low cut lines are not clamped at 150.
      if (yName === tt("ui.tournament.average", "Average")) {
        const nums = [
          ...collectNumericValues(dataSeries),
          ...collectNumericValues(cutLines),
        ];
        if (Array.isArray(series?.cut_line_series)) {
          series.cut_line_series.forEach((line) => {
            nums.push(...collectNumericValues(line?.data));
          });
        } else if (series?.cut_lines_avg_dynamic && typeof series.cut_lines_avg_dynamic === "object") {
          Object.values(series.cut_lines_avg_dynamic).forEach((vals) => {
            nums.push(...collectNumericValues(vals));
          });
        }
        if (Array.isArray(extraLines)) {
          extraLines.forEach((line) => nums.push(...collectNumericValues(line?.data)));
        }
        if (nums.length > 0) {
          const minVal = Math.min(...nums);
          const maxVal = Math.max(...nums);
          const padding = Math.max(3, (maxVal - minVal) * 0.05);
          yMin = Math.floor((minVal - padding) / 5) * 5;
          yMax = Math.ceil((maxVal + padding) / 5) * 5;
          // Keep tournament average plots readable without hard-floor clipping.
          yMin = Math.max(0, yMin);
          yMax = Math.min(300, yMax);
          if (yMax <= yMin) yMax = yMin + 10;
        }
      }
      // Auto-scale rank chart to real participant count (1..n), not a fixed cap.
      if (yName === tt("ui.tournament.rank", "Rank")) {
        const nums = [
          ...collectNumericValues(dataSeries),
          ...collectNumericValues(cutLines),
        ];
        const participantCount = Number(series?.participant_count);
        const maxObservedRank = nums.length > 0 ? Math.max(...nums) : 1;
        const rankCap = Number.isFinite(participantCount) && participantCount > 0
          ? Math.max(participantCount, maxObservedRank)
          : maxObservedRank;
        yMin = 1;
        yMax = Math.max(1, Math.ceil(rankCap));
      }

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

      const dynamicCutSeries = [];
      const positionCutSeries = [];
      if (cutLineMode === "dynamic" && yName === tt("ui.tournament.average", "Average") && Array.isArray(series.cut_line_series)) {
        const lines = [...series.cut_line_series].sort((a, b) => Number(a?.round_number || 0) - Number(b?.round_number || 0));
        const segments = [];
        lines.forEach((line) => {
          const raw = line?.data;
          if (!Array.isArray(raw)) return;
          const pts = buildPointSeries(raw, 0, maxX, false, false);
          if (!pts.length) return;
          segments.push(pts);
        });
        if (segments.length) {
          const stitched = [...segments[0]];
          for (let i = 1; i < segments.length; i += 1) {
            const prev = segments[i - 1];
            const next = segments[i];
            const prevLast = prev[prev.length - 1];
            const nextFirst = next[0];
            if (prevLast && nextFirst) {
              // Add a vertical jump at stage transition (e.g. x=6.5).
              const boundaryX = (Number(prevLast[0]) + Number(nextFirst[0])) / 2;
              stitched.push([boundaryX, Number(prevLast[1])]);
              stitched.push([boundaryX, Number(nextFirst[1])]);
            }
            stitched.push(...next);
          }
          dynamicCutSeries.push({
            name: tt("ui.tournament.cut_line", "Cut Line"),
            type: "line",
            data: stitched,
            smooth: false,
            connectNulls: false,
            showSymbol: false,
            lineStyle: { width: 2, type: "dashed", color: colorCutUnified },
            itemStyle: { color: colorCutUnified },
            z: 1,
          });
        }
      } else if (cutLineMode === "dynamic" && yName === tt("ui.tournament.average", "Average") && series.cut_lines_avg_dynamic && typeof series.cut_lines_avg_dynamic === "object") {
        // Backward-compatible fallback in case browser still receives legacy payload shape.
        const keys = Object.keys(series.cut_lines_avg_dynamic).sort((a, b) => {
          const na = Number(String(a).replace("round_", ""));
          const nb = Number(String(b).replace("round_", ""));
          return na - nb;
        });
        keys.forEach((key) => {
          const raw = series.cut_lines_avg_dynamic[key];
          if (!Array.isArray(raw)) return;
          const pts = buildPointSeries(raw, 0, maxX, false, false);
          if (!pts.length) return;
          dynamicCutSeries.push({
            name: tt("ui.tournament.cut_line", "Cut Line"),
            type: "line",
            data: pts,
            smooth: false,
            connectNulls: false,
            showSymbol: false,
            lineStyle: { width: 2, type: "dashed", color: colorCutUnified },
            itemStyle: { color: colorCutUnified },
            z: 1,
          });
        });
      }

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
      // Position chart should always show cut-position references as horizontal lines.
      if (yName === tt("ui.tournament.rank", "Rank")) {
        const cutValues = (cutLines || [])
          .map((v) => Number(v))
          .filter((v) => Number.isFinite(v));
        cutValues.forEach((v, idx) => {
          const y = Math.max(yMin, Math.min(yMax, v));
          const startX = idx === 0 ? 0 : (roundBoundaries[idx - 1] ?? 0);
          const endX = roundBoundaries[idx] ?? maxX;
          markLines.push([
            { coord: [startX, y], lineStyle: { color: colorCutUnified, type: "dashed", width: 2 } },
            { coord: [endX, y] },
          ]);
          // Sample the horizontal cut line at integer game ticks so tooltip
          // follows player progression game-by-game.
          const sampled = [];
          for (let game = 1; game <= totalGames; game += 1) {
            if (game > startX && game <= endX) {
              sampled.push([game, y]);
            }
          }
          if (!sampled.length) return;
          positionCutSeries.push({
            name: tt("ui.tournament.cut_line", "Cut Line"),
            type: "line",
            data: sampled,
            smooth: false,
            connectNulls: false,
            showSymbol: false,
            lineStyle: { width: 2, type: "dashed", color: colorCutUnified },
            itemStyle: { color: colorCutUnified },
            z: 1,
          });
        });
      }

      const extraOverlaySeries = (extraLines || []).map((line) => {
        const mapped = buildPointSeries(line?.data || [], 0, maxX, false, false);
        return {
          name: line.name || tt("ui.tournament.reference", "Reference"),
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
          tooltip: {
            trigger: "axis",
            formatter: function (params) {
              const rows = Array.isArray(params) ? [...params] : [params];
              const isRankChart = yName === tt("ui.tournament.rank", "Rank");
              rows.sort((a, b) => {
                const av = Number(a?.value?.[1]);
                const bv = Number(b?.value?.[1]);
                if (isRankChart) {
                  const aNum = Number.isFinite(av) ? av : Number.POSITIVE_INFINITY;
                  const bNum = Number.isFinite(bv) ? bv : Number.POSITIVE_INFINITY;
                  return aNum - bNum; // rank: lower is better
                }
                const aNum = Number.isFinite(av) ? av : Number.NEGATIVE_INFINITY;
                const bNum = Number.isFinite(bv) ? bv : Number.NEGATIVE_INFINITY;
                return bNum - aNum; // average: higher is better
              });
              if (!rows.length) return "";
              const axisRaw = Number(rows[0]?.axisValue);
              const gameNo = Number.isFinite(axisRaw) ? Math.round(axisRaw) : null;
              const scoreAtGame =
                gameNo && Array.isArray(series?.game_score_series)
                  ? series.game_score_series[gameNo - 1]
                  : null;
              const scoreText =
                scoreAtGame !== null && scoreAtGame !== undefined && scoreAtGame !== ""
                  ? String(scoreAtGame)
                  : "-";
              const axisLabel =
                gameNo !== null ? `${tt("ui.tournament.game", "Game")} ${gameNo}: ${scoreText}` : "";
              const lines = rows.map((r) => {
                const marker = r.marker || "";
                const name = r.seriesName || "";
                const y = Number(r?.value?.[1]);
                const val = Number.isFinite(y)
                  ? (isRankChart ? String(Math.round(y)) : y.toFixed(1))
                  : "-";
                return `${marker}${name}: <b>${val}</b>`;
              });
              return [axisLabel, ...lines].join("<br/>");
            },
          },
          legend: { show: false },
          grid: { top: "10%", right: "5%", bottom: "14%", left: "10%", containLabel: true },
          xAxis: {
            type: "value",
            name: tt("ui.tournament.game", "Game"),
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
            ...dynamicCutSeries,
            ...positionCutSeries,
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
      tt("ui.tournament.average", "Average"),
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
        {
          name: tt("ui.tournament.lowest_average", "Lowest Average"),
          data: series.tournament_lowest_avg_series || [],
          dashed: true,
          color:
            (typeof getSemanticColor === "function" && getSemanticColor("negative")) || "#D62728",
          width: 2,
        },
      ]
    );
    renderLine(
      "tournamentPlayerPosChart",
      (series.position_series || []).map((v) => Number(v)),
      tt("ui.tournament.rank", "Rank"),
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
      const colorLowestAvg =
        (typeof getSemanticColor === "function" && getSemanticColor("negative")) || "#D62728";

      const item = (label, color, dashed = false) => `
        <div class="d-flex align-items-center">
          <span style="display:inline-block;width:26px;height:0;border-top:3px ${dashed ? "dashed" : "solid"} ${color};margin-right:8px;"></span>
          <span>${label}</span>
        </div>
      `;
      const dynamicCutLegend = cutLineMode === "dynamic"
        ? [item(tt("ui.tournament.cut_line_pace", "Cut Line (pace)"), colorCutUnified, true)]
        : [item(tt("ui.tournament.cut_line", "Cut Line"), colorCutUnified, true)];
      legendContainer.innerHTML = [
        item(playerName, colorPlayer, false),
        item(tt("ui.tournament.tournament_leader", "Tournament Leader"), colorLeader, true),
        item(tt("ui.tournament.lowest_average", "Lowest Average"), colorLowestAvg, true),
        item(tt("ui.tournament.round_boundary", "Round Boundary"), colorRoundBoundary, false),
        ...dynamicCutLegend,
      ].join("");
    }
  }

  async function onPlayerChanged() {
    const season = currentFilters.season;
    const tournament = currentFilters.tournament;
    const input = document.getElementById("tournamentPlayerInput");
    const rawPlayer = (input?.value || "").trim();
    const player = resolvePlayerName(rawPlayer, tournamentPlayers);
    if (!season || !tournament || !player) {
      if (input && !player) input.value = "";
      setPlayerMode(false);
      renderPlayerSection(null);
      syncUrlWithFilters();
      return;
    }
    if (input) input.value = player;
    const exists = tournamentPlayers.some((p) => String(p).toLowerCase() === player.toLowerCase());
    if (!exists) {
      setPlayerMode(false);
      renderPlayerSection(null);
      syncUrlWithFilters();
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
      syncUrlWithFilters();
    } catch (err) {
      console.error("Failed to load player section:", err);
      setPlayerMode(false);
      renderPlayerSection(null);
      syncUrlWithFilters();
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
    updateLeaderboardHeader(section);
    renderTable("tournamentLeaderboardTable", section.leaderboard);
    setRoundResultsVisibility();
    renderRoundResultsHeatmapControls();
    if (String(currentFilters.round || "").trim()) {
      updateRoundResultsHeader(section);
      renderTable("tournamentRoundResultsTable", section.round_results);
      currentRoundResultsHeatmapRange =
        section?.round_results?.metadata?.heatmap_ranges?.game_score || DEFAULT_GAME_HEATMAP_RANGE;
      requestAnimationFrame(() => {
        requestAnimationFrame(() => scheduleRoundResultsHeatmapApply());
      });
      // Extra pass for slower initial Tabulator mounts.
      window.setTimeout(() => scheduleRoundResultsHeatmapApply(20, 150), 1200);
    }
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
    const roundItems = [{ value: "", label: tt("ui.tournament.all_latest", "Total") }].concat(
      rounds.map((r) => ({
        value: String(r.round_number),
        label: `${r.round_number} - ${r.round_name || tt("ui.tournament.round", "Round")}`,
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
    refreshTournamentUiText();
    renderRoundResultsHeatmapControls();
    const params = new URLSearchParams(window.location.search);
    const deepLinkedPlayer = (params.get("player") || "").trim();
    const seasons = await getAvailableSeasons();
    const seasonItems = seasons.map((s) => ({ value: String(s), label: String(s) }));
    currentFilters.season = pickValue(seasonItems, params.get("season"));

    await refreshSeasonButtons();

    currentFilters.tournament = params.get("tournament") || "";
    await refreshTournamentButtons();

    currentFilters.round = params.get("round") || "";
    await refreshRoundButtons();

    await applyFiltersAndRender(true);

    if (deepLinkedPlayer) {
      const input = document.getElementById("tournamentPlayerInput");
      if (input) {
        input.value = resolvePlayerName(deepLinkedPlayer, tournamentPlayers) || deepLinkedPlayer;
        await onPlayerChanged();
      }
    }

    document.getElementById("tournamentPlayerInput")?.addEventListener("change", onPlayerChanged);
    document.getElementById("tournamentPlayerInput")?.addEventListener("blur", onPlayerChanged);
    window.addEventListener("translationsLoaded", async () => {
      refreshTournamentUiText();
      await applyFiltersAndRender(true);
      await refreshRoundButtons();
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
