(function () {
  let currentTournamentGender = null;
  /** Synced in renderSection; used when leaving player mode so conditional overview cards keep correct display. */
  let lastOverviewHasPostQual = false;
  let lastOverviewHasKoRr = false;

  function tt(key, fallback) {
    if (typeof t === "function") return t(key, fallback);
    return fallback || key;
  }

  function localizeTournamentCardTitle(rawTitle) {
    const title = String(rawTitle || "").trim();
    const fem = currentTournamentGender === "f";
    const map = {
      Tournament: () => tt("ui.tournament.card.tournament", "Tournament"),
      "Current Round": () => tt("ui.tournament.card.current_round", "Current Round"),
      "Cut Line": () => tt("ui.tournament.card.cut_line", "Cut Line"),
      "Tournament Leader": () =>
        fem
          ? tt("ui.tournament.card.tournament_leader_f", "Tournament Leader")
          : tt("ui.tournament.card.tournament_leader", "Tournament Leader"),
      Participants: () =>
        fem
          ? tt("ui.tournament.card.participants_f", "Participants")
          : tt("ui.tournament.card.participants", "Participants"),
      "Stage Winner": () =>
        fem
          ? tt("ui.tournament.card.stage_winner_f", "Stage Winner")
          : tt("ui.tournament.card.stage_winner", "Stage Winner"),
      "Tournament Winner": () =>
        fem
          ? tt("ui.tournament.card.tournament_winner_f", "Tournament Winner")
          : tt("ui.tournament.card.tournament_winner", "Tournament Winner"),
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

  /** Enable with ?tournamentDebug=1 or localStorage.setItem("bowlyzerTournamentStatsDebug","1") */
  function tournamentStatsDebugEnabled() {
    try {
      return (
        new URLSearchParams(window.location.search).has("tournamentDebug") ||
        localStorage.getItem("bowlyzerTournamentStatsDebug") === "1"
      );
    } catch (e) {
      return false;
    }
  }

  /** DevTools: filter console by `[tournament-stats]`. */
  function dbgTournamentStats(phase, detail) {
    if (!tournamentStatsDebugEnabled()) return;
    console.info("[tournament-stats]", phase, detail);
  }

  /** Map calendar year in URL (2026) to bowling season label (25/26) when present in API list. */
  function normalizeSeasonFromUrl(urlSeason, seasonsFromApi) {
    const s = (urlSeason || "").trim();
    const list = Array.isArray(seasonsFromApi) ? seasonsFromApi.map(String) : [];
    if (!s || !list.length) return s;
    if (list.includes(s)) return s;
    const m = /^(\d{4})$/.exec(s);
    if (m) {
      const y = parseInt(m[1], 10);
      if (Number.isFinite(y)) {
        const candidate = `${String(y - 1).slice(-2)}/${String(y).slice(-2)}`;
        if (list.includes(candidate)) return candidate;
      }
    }
    return s;
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function koBracketNormName(n) {
    return String(n || "")
      .trim()
      .toLowerCase();
  }

  function koBracketStripNoShow(name) {
    const s = String(name || "").trim();
    const low = s.toLowerCase();
    if (low.endsWith("(no show)")) {
      const cut = s.slice(0, s.lastIndexOf("(")).trim();
      return cut || s;
    }
    return s;
  }

  function koBracketSideKey(name) {
    return koBracketNormName(koBracketStripNoShow(name));
  }

  function koMatchWinnerName(m) {
    if (!m || !m.winner) return "";
    if (m.winner === "a") return String(m.side_a?.name || "");
    if (m.winner === "b") return String(m.side_b?.name || "");
    return "";
  }

  /** True if this SF match includes the given QF winner (e.g. to align QF columns with the correct semi). */
  function koSfContainsWinner(sfM, winnerName) {
    if (!sfM || !winnerName) return false;
    const wk = koBracketSideKey(winnerName);
    if (!wk) return false;
    return (
      koBracketSideKey(sfM.side_a?.name || "") === wk ||
      koBracketSideKey(sfM.side_b?.name || "") === wk
    );
  }

  function koBracketIsByeDisplayName(name) {
    const low = String(name || "").trim().toLowerCase();
    if (!low) return true;
    if (low.includes("nicht angetreten")) return true;
    return low === "bye" || low === "freilos" || low === "tbd";
  }

  /** Fixed 6-player KO seeds: QF1 = 3 vs 6, QF2 = 4 vs 5; SF byes = 1 & 2. */
  function buildKoBracketSeedByNameKey(byKey) {
    const map = Object.create(null);
    const set = (nm, seed) => {
      const k = koBracketSideKey(nm);
      if (k && seed != null) map[k] = seed;
    };
    const get = (nm) => map[koBracketSideKey(nm)];

    const qf1 = byKey.QF1;
    const qf2 = byKey.QF2;
    const sf1 = byKey.SF1;
    const sf2 = byKey.SF2;
    const fin = byKey.F;

    if (qf1) {
      set(qf1.side_a?.name, 3);
      set(qf1.side_b?.name, 6);
    }
    if (qf2) {
      set(qf2.side_a?.name, 4);
      set(qf2.side_b?.name, 5);
    }

    const tagSf = (sfM, byeSeed) => {
      if (!sfM) return;
      [sfM.side_a, sfM.side_b].forEach((side) => {
        const nm = side?.name;
        if (!nm || koBracketIsByeDisplayName(nm)) return;
        if (get(nm) != null) return;
        if (byeSeed != null) set(nm, byeSeed);
      });
    };

    if (sf1) tagSf(sf1, 1);
    if (sf2) tagSf(sf2, 2);

    if (fin) {
      ["side_a", "side_b"].forEach((sk) => {
        const nm = fin[sk]?.name;
        if (!nm || koBracketIsByeDisplayName(nm)) return;
        if (get(nm) != null) return;
        for (const sf of [sf1, sf2]) {
          if (!sf) continue;
          for (const side of [sf.side_a, sf.side_b]) {
            if (!side?.name) continue;
            if (koBracketSideKey(side.name) !== koBracketSideKey(nm)) continue;
            const s = get(side.name);
            if (s != null) {
              set(nm, s);
              return;
            }
          }
        }
      });
    }

    return map;
  }

  function getRainbowPaletteColor(index, fallback) {
    if (window.ColorUtils && typeof window.ColorUtils.getPaletteColor === "function") {
      try {
        return window.ColorUtils.getPaletteColor(Number(index));
      } catch (_e) {
        /* ignore */
      }
    }
    return fallback;
  }

  function renderKoBracketInner(bracket) {
    const matches = bracket && Array.isArray(bracket.matches) ? bracket.matches : [];
    if (!matches.length) return "";
    const byKey = Object.fromEntries(matches.map((m) => [m.key, m]));
    const woLabel = tt("ui.tournament.walkover", "Walkover");
    const inferredNote = tt(
      "ui.tournament.ko_sf2_inferred_note",
      "Semifinal 2 was not present in the export; it is shown here as a walkover so the bracket matches the live draw."
    );
    const phaseLabel = (ph) => {
      if (ph === "qf") return tt("ui.tournament.phase_qf", "Quarterfinal");
      if (ph === "sf") return tt("ui.tournament.phase_sf", "Semifinal");
      if (ph === "final") return tt("ui.tournament.phase_final", "Final");
      return tt("ui.tournament.phase_ko", "Knockout");
    };

    const fa = bracket.finalist_a || "";
    const fb = bracket.finalist_b || "";
    const nfa = koBracketNormName(fa);
    const nfb = koBracketNormName(fb);
    const pathA = new Set(bracket.path_keys_a || []);
    const pathB = new Set(bracket.path_keys_b || []);
    const idxA = bracket.palette_index_a != null ? bracket.palette_index_a : 2;
    const idxB = bracket.palette_index_b != null ? bracket.palette_index_b : 8;
    const colA = getRainbowPaletteColor(idxA, "#8CBF8A");
    const colB = getRainbowPaletteColor(idxB, "#A04CBF");
    const focusPlayerRaw =
      bracket.focus_player != null && String(bracket.focus_player).trim() !== ""
        ? String(bracket.focus_player).trim()
        : "";
    const focusKey = focusPlayerRaw ? koBracketSideKey(focusPlayerRaw) : "";
    const focusPaletteRaw =
      bracket.focus_palette_index != null ? Number(bracket.focus_palette_index) : Number.NaN;
    const focusPaletteIdx = Number.isFinite(focusPaletteRaw) ? focusPaletteRaw : idxA;
    const colFocus = getRainbowPaletteColor(focusPaletteIdx, "#8CBF8A");
    const matchHasFocus = (m) => {
      if (!focusKey || !m) return false;
      return (
        koBracketSideKey(m.side_a?.name) === focusKey || koBracketSideKey(m.side_b?.name) === focusKey
      );
    };
    const focusWonMatch = (m) => {
      if (!focusKey || !m || !m.winner) return false;
      if (m.winner === "a") return koBracketSideKey(m.side_a?.name) === focusKey;
      if (m.winner === "b") return koBracketSideKey(m.side_b?.name) === focusKey;
      return false;
    };
    const seedByKey = buildKoBracketSeedByNameKey(byKey);
    const seedFor = (name) => seedByKey[koBracketSideKey(name)];

    const qf1 = byKey.QF1;
    const qf2 = byKey.QF2;
    const sf1 = byKey.SF1;
    const sf2 = byKey.SF2;
    const fin = byKey.F;

    const winnerLaneColor = (m) => {
      if (!m) return null;
      if (m.winner === "a") return colA;
      if (m.winner === "b") return colB;
      return null;
    };

    const matchPathStyle = (m) => {
      if (focusKey) {
        if (!matchHasFocus(m)) {
          return "border: 1px solid rgba(0,0,0,0.12); box-shadow: none;";
        }
        if (focusWonMatch(m)) {
          return `border-color: ${colFocus}; border-width: 2px; box-shadow: none;`;
        }
        return "border: 1px solid rgba(0,0,0,0.14); box-shadow: none;";
      }
      const pk = m.key;
      const onA = pathA.has(pk);
      const onB = pathB.has(pk);
      const isFinal = pk === "F";
      if (isFinal && onA && onB) {
        const winCol = winnerLaneColor(m);
        if (winCol) {
          // Outline only in the winner's lane color; name rows keep per-finalist lane colors via rowLaneClass.
          return `border-color: ${winCol}; border-width: 2px; box-shadow: none;`;
        }
        return `box-shadow: inset 5px 0 0 ${colA}, inset -5px 0 0 ${colB}; border-color: rgba(0,0,0,0.12);`;
      }
      if (onA && !onB) return `border-color: ${colA}; border-width: 2px;`;
      if (onB && !onA) return `border-color: ${colB}; border-width: 2px;`;
      if (onA && onB && !isFinal) {
        return `border-top: 3px solid ${colA}; border-bottom: 3px solid ${colB};`;
      }
      return "";
    };

    const rowLaneClass = (name) => {
      if (focusKey) {
        if (koBracketSideKey(name) === focusKey) return " ko-bracket-row--lane-a";
        return "";
      }
      const n = koBracketNormName(name);
      if (nfa && n === nfa) return " ko-bracket-row--lane-a";
      if (nfb && n === nfb) return " ko-bracket-row--lane-b";
      return "";
    };

    const qf1w = koMatchWinnerName(qf1);
    const qf2w = koMatchWinnerName(qf2);

    /** When the export labels SF1/SF2 in reverse vs QF feed (e.g. form order), place each QF under the semi that contains its winner. */
    let sfUnderQf1 = sf1;
    let sfUnderQf2 = sf2;
    if (sf1 && sf2 && qf1w && qf2w) {
      if (koSfContainsWinner(sf2, qf1w) && !koSfContainsWinner(sf1, qf1w)) {
        sfUnderQf1 = sf2;
        sfUnderQf2 = sf1;
      }
    }

    const sfOriginSuffix = (sideName) => {
      const raw = String(sideName || "").trim();
      if (!raw) return "";
      const sk = koBracketSideKey(raw);
      if (!sk) return "";
      if (qf1w && sk === koBracketSideKey(qf1w)) {
        return ` <span class="ko-bracket-origin text-muted">(${escapeHtml(tt("ui.tournament.tag_qf1", "QF1"))})</span>`;
      }
      if (qf2w && sk === koBracketSideKey(qf2w)) {
        return ` <span class="ko-bracket-origin text-muted">(${escapeHtml(tt("ui.tournament.tag_qf2", "QF2"))})</span>`;
      }
      return "";
    };

    const bracketSeedSuffix = (side) => {
      const sn = seedFor(side.name);
      if (sn == null) return "";
      const title = escapeHtml(tt("ui.tournament.bracket_seed_title", "Draw seed"));
      return ` <span class="ko-bracket-seed text-muted" title="${title}">(#${escapeHtml(String(sn))})</span>`;
    };

    const scratchSeriesSummaryHtml = (m) => {
      if (!m || m.walkover || !(m.scratch_series || m.scratch_final)) return null;
      const ta = Number(m.scratch_total_a ?? 0);
      const tb = Number(m.scratch_total_b ?? 0);
      const taStr = escapeHtml(String(Math.round(ta)));
      const tbStr = escapeHtml(String(Math.round(tb)));
      let inner;
      if (m.winner === "a") {
        inner = `<strong>${taStr}</strong>\u2013${tbStr}`;
      } else if (m.winner === "b") {
        inner = `${taStr}\u2013<strong>${tbStr}</strong>`;
      } else if (ta > tb) {
        inner = `<strong>${taStr}</strong>\u2013${tbStr}`;
      } else if (tb > ta) {
        inner = `${taStr}\u2013<strong>${tbStr}</strong>`;
      } else {
        inner = `${taStr}\u2013${tbStr}`;
      }
      const isFinal = m.phase === "final";
      const title = escapeHtml(
        isFinal
          ? tt("ui.tournament.scratch_total_title", "Scratch total (2 games)")
          : tt("ui.tournament.scratch_total_match", "Scratch total")
      );
      return `<span class="ko-bracket-scratch-total" title="${title}">${inner}</span>`;
    };

    const seriesGamesWonHtml = (m, a, b) => {
      const wa = Number(a.games_won ?? 0);
      const wb = Number(b.games_won ?? 0);
      const wsa = escapeHtml(String(wa));
      const wsb = escapeHtml(String(wb));
      if (m.winner === "a") return `<strong>${wsa}</strong>\u2013${wsb}`;
      if (m.winner === "b") return `${wsa}\u2013<strong>${wsb}</strong>`;
      return `${wsa}\u2013${wsb}`;
    };

    const renderMatchCard = (m, decor) => {
      if (!m) return "";
      decor = decor || {};
      const a = m.side_a || {};
      const b = m.side_b || {};
      const aHi = a.highlight ? " ko-bracket-row--hi" : "";
      const bHi = b.highlight ? " ko-bracket-row--hi" : "";
      const aWin = m.winner === "a";
      const bWin = m.winner === "b";
      const pinTxt = (m.pin_games || [])
        .map((g, i) => `G${i + 1}: ${g[0]}\u2013${g[1]}`)
        .join(" \u00b7 ");
      const pinGamesLine =
        pinTxt && !m.walkover
          ? `<div class="ko-bracket-per-game small text-muted mt-1">${escapeHtml(pinTxt)}</div>`
          : "";
      const woLine = m.walkover
        ? `<div class="ko-bracket-wo mt-1"><span class="badge bg-secondary text-white">${escapeHtml(woLabel)}</span></div>`
        : "";
      const scratchSeries = scratchSeriesSummaryHtml(m);
      const summaryLineHtml = scratchSeries ? scratchSeries : seriesGamesWonHtml(m, a, b);
      const inferred = m.inferred
        ? ` <span class="badge rounded-pill bg-light text-dark border ko-bracket-inferred-pill">${escapeHtml(tt("ui.tournament.inferred", "Inferred"))}</span>`
        : "";
      const pathStyle = matchPathStyle(m);
      const styleAttr = pathStyle ? ` style="${pathStyle.replace(/"/g, "&quot;")}"` : "";

      const nameInner = (side, sideKey) => {
        const win = (sideKey === "a" && aWin) || (sideKey === "b" && bWin);
        const tick = win ? "<strong>\u2713 </strong>" : "";
        const nm = escapeHtml(side.name || "");
        const body = win ? `${tick}<strong>${nm}</strong>` : `${tick}${nm}`;
        const origin = m.phase === "sf" && decor.sfOrigin ? sfOriginSuffix(side.name) : "";
        const seed = bracketSeedSuffix(side);
        return `<span>${body}</span>${seed}${origin}`;
      };

      return `
        <div class="ko-bracket-match"${styleAttr} data-phase="${escapeHtml(m.phase || "")}" data-ko-key="${escapeHtml(m.key || "")}">
          <div class="ko-bracket-phase-label">${escapeHtml(phaseLabel(m.phase))} \u00b7 ${escapeHtml(m.label || m.key || "")}${inferred}</div>
          <div class="ko-bracket-row${aHi}${rowLaneClass(a.name)}">
            ${nameInner(a, "a")}
          </div>
          <div class="ko-bracket-row${bHi}${rowLaneClass(b.name)}">
            ${nameInner(b, "b")}
          </div>
          ${pinGamesLine}
          <div class="ko-bracket-series small text-muted text-end mt-1">${summaryLineHtml}</div>
          ${woLine}
        </div>`;
    };

    const wireFeedVert = `<svg class="ko-bracket-wires ko-bracket-wires--feed" viewBox="0 0 10 18" preserveAspectRatio="xMidYMin meet" aria-hidden="true">
      <path fill="none" stroke="currentColor" stroke-width="1.15" vector-effect="non-scaling-stroke" d="M 5 0 V 18" />
    </svg>`;
    const wireQfSfMerge = `<svg class="ko-bracket-wires ko-bracket-merge-qf-sf" viewBox="0 0 100 22" preserveAspectRatio="none" aria-hidden="true">
      <path fill="none" stroke="currentColor" stroke-width="1.1" vector-effect="non-scaling-stroke"
        d="M 25 1 V 9 H 50 M 75 1 V 9 H 50 M 50 9 V 20" />
    </svg>`;
    const wireSfF = `<svg class="ko-bracket-wires" viewBox="0 0 100 22" preserveAspectRatio="none" aria-hidden="true">
      <path fill="none" stroke="currentColor" stroke-width="1.1" vector-effect="non-scaling-stroke"
        d="M 35 1 V 9 H 50 M 65 1 V 9 H 50 M 50 9 V 20" />
    </svg>`;

    const hasInferred = matches.some((m) => m.inferred);
    const note = hasInferred ? `<p class="text-muted small mt-2 mb-0">${escapeHtml(inferredNote)}</p>` : "";

    const hasQfPair = qf1 && qf2;
    const hasTwoSfs = !!(sf1 && sf2);

    const fHtml = renderMatchCard(fin, {});
    const fBlock =
      fHtml.trim() === ""
        ? ""
        : `<div class="ko-bracket-tier ko-bracket-tier--final">
          <div class="ko-bracket-tier-label text-muted small text-uppercase">${escapeHtml(tt("ui.tournament.tier_final", "Final"))}</div>
          <div class="ko-bracket-tier-matches ko-bracket-tier-matches--center">${fHtml}</div>
        </div>`;

    let bodyInner = "";

    if (hasQfPair && hasTwoSfs) {
      const qf1Html = renderMatchCard(qf1, {});
      const qf2Html = renderMatchCard(qf2, {});
      const sfLeftHtml = renderMatchCard(sfUnderQf1, { sfOrigin: true });
      const sfRightHtml = renderMatchCard(sfUnderQf2, { sfOrigin: true });
      bodyInner = `
        <div class="ko-bracket-tier ko-bracket-tier--qf">
          <div class="ko-bracket-tier-label text-muted small text-uppercase text-center">${escapeHtml(tt("ui.tournament.tier_qf_sf_feed", "Quarterfinals \u2192 Semifinals"))}</div>
          <div class="ko-bracket-doubles">
            <div class="ko-bracket-feed">
              ${qf1Html}
              ${wireFeedVert}
              ${sfLeftHtml}
            </div>
            <div class="ko-bracket-feed">
              ${qf2Html}
              ${wireFeedVert}
              ${sfRightHtml}
            </div>
          </div>
        </div>
        <div class="ko-bracket-final-stack">
          ${fHtml.trim() !== "" ? wireSfF : ""}
          ${fBlock}
        </div>`;
    } else if (hasQfPair && sf1 && !sf2) {
      const qf1Html = renderMatchCard(qf1, {});
      const qf2Html = renderMatchCard(qf2, {});
      const sf1Html = renderMatchCard(sf1, { sfOrigin: true });
      bodyInner = `
        <div class="ko-bracket-tier ko-bracket-tier--qf">
          <div class="ko-bracket-tier-label text-muted small text-uppercase text-center">${escapeHtml(tt("ui.tournament.tier_qf", "Quarterfinals"))}</div>
          <div class="ko-bracket-doubles ko-bracket-doubles--single-sf">
            <div class="ko-bracket-qf-pair">${qf1Html}</div>
            <div class="ko-bracket-qf-pair">${qf2Html}</div>
            ${wireQfSfMerge}
            <div class="ko-bracket-sf-span">${sf1Html}</div>
          </div>
        </div>
        <div class="ko-bracket-final-stack">
          ${fHtml.trim() !== "" ? wireSfF : ""}
          ${fBlock}
        </div>`;
    } else {
      const qfKeys = ["QF1", "QF2"];
      const qfHtml = qfKeys.map((k) => renderMatchCard(byKey[k], {})).join("");
      const sfOrdered =
        sf1 && sf2 ? [sfUnderQf1, sfUnderQf2] : [byKey.SF1, byKey.SF2].filter(Boolean);
      const sfHtml = sfOrdered.map((m) => renderMatchCard(m, { sfOrigin: true })).join("");
      const qfBlock =
        qfHtml.trim() === ""
          ? ""
          : `<div class="ko-bracket-tier ko-bracket-tier--qf">
          <div class="ko-bracket-tier-label text-muted small text-uppercase">${escapeHtml(tt("ui.tournament.tier_qf", "Quarterfinals"))}</div>
          <div class="ko-bracket-tier-matches">${qfHtml}</div>
        </div>
        ${qfHtml.trim() !== "" && sfHtml.trim() !== "" ? wireQfSfMerge : ""}`;
      const sfBlock =
        sfHtml.trim() === ""
          ? ""
          : `<div class="ko-bracket-tier ko-bracket-tier--sf">
          <div class="ko-bracket-tier-label text-muted small text-uppercase">${escapeHtml(tt("ui.tournament.tier_sf", "Semifinals"))}</div>
          <div class="ko-bracket-tier-matches">${sfHtml}</div>
        </div>
        ${fHtml.trim() !== "" ? wireSfF : ""}`;
      bodyInner = `${qfBlock}${sfBlock}${fBlock}`;
    }

    const treeLaneA = focusKey ? colFocus : colA;
    const treeLaneB = focusKey ? colFocus : colB;
    return `
      <div class="ko-bracket-tree" style="--ko-lane-a:${treeLaneA};--ko-lane-b:${treeLaneB};">
        ${bodyInner}
        ${note}
      </div>`;
  }

  function renderKoBracketCard(bracket) {
    const inner = renderKoBracketInner(bracket);
    if (!inner) return "";
    const title = tt("ui.tournament.ko_bracket_title", "Knockout bracket");
    return `
      <div class="card mb-4 tournament-ko-bracket-card">
        <div class="card-header"><h5 class="mb-0">${escapeHtml(title)}</h5></div>
        <div class="card-body p-2 p-md-3">${inner}</div>
      </div>`;
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
      renderRoundResultsHeatmapControls("tournamentKoFinaleRoundResultsHeatmapControls");
      renderRoundResultsHeatmapControls("tournamentPlayerRoundResultsHeatmapControls");
      applyRoundResultsHeatmapToTable("tournamentRoundResultsTable", currentRoundResultsHeatmapRange);
      applyRoundResultsHeatmapToTable("tournamentKoFinaleRoundResultsTable", currentRoundResultsHeatmapRange);
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
      const okKo = applyRoundResultsHeatmapToTable("tournamentKoFinaleRoundResultsTable", currentRoundResultsHeatmapRange);
      const okPlayer = applyRoundResultsHeatmapToTable("tournamentPlayerRoundTable", currentPlayerRoundHeatmapRange);
      const ok = okOverview || okKo || okPlayer;
      if (ok || attempts >= maxAttempts) return;
      window.setTimeout(tick, delayMs);
    };
    tick();
  }

  function updateLeaderboardHeader(section) {
    const headerEl = document.querySelector("#tournamentLeaderboardCard .card-header h5");
    if (!headerEl) return;
    if (section?.is_ko_finale_round) {
      headerEl.textContent = tt("ui.tournament.ko_placements_title", "Knockout final standings");
      return;
    }
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
        const titleAttr =
          item.title != null && String(item.title).trim() !== ""
            ? ` title="${escapeAttr(String(item.title))}"`
            : "";
        return `
          <button type="button" class="btn btn-sm ${active ? "btn-primary" : "btn-outline-primary"} me-2 mb-2"${titleAttr} data-value="${escapeAttr(value)}">
            ${escapeHtml(label)}
          </button>
        `;
      })
      .join("");
    container.querySelectorAll("button[data-value]").forEach((btn) => {
      btn.addEventListener("click", () => onSelect(btn.getAttribute("data-value") || ""));
    });
  }
  function setPlayerMode(enabled) {
    const ids = [
      "tournamentCards",
      "tournamentBestEfforts",
      "tournamentLeaderboardCard",
      "tournamentRoundResultsCard",
      "tournamentKoBracketOverview",
    ];
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.style.display = enabled ? "none" : "";
    });
    const pqCard = document.getElementById("tournamentPostQualificationCard");
    if (pqCard) {
      if (enabled) pqCard.style.display = "none";
      else pqCard.style.display = lastOverviewHasPostQual ? "" : "none";
    }
    const koRrCard = document.getElementById("tournamentKoFinaleRoundResultsCard");
    if (koRrCard) {
      if (enabled) koRrCard.style.display = "none";
      else koRrCard.style.display = lastOverviewHasKoRr ? "" : "none";
    }
    const roundFilter = document.getElementById("tournamentRoundFilterGroup");
    if (roundFilter) roundFilter.style.display = enabled ? "none" : "";
  }

  function getSelectedPlayer() {
    const input = document.getElementById("tournamentPlayerInput");
    return (input?.value || "").trim();
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

  const DEFAULT_PLAYER_CARD_LAYOUT = [
    "summary_final_position",
    "summary_average",
    "summary_best_position",
    "best_highest_game",
    "best_highest_block",
  ];

  function buildPlayerMetricCardHtml(cardId, payload) {
    const s = payload.summary || {};
    const b = payload.best_efforts || {};
    const hp = b.handicap_profile;
    if (cardId === "summary_final_position") {
      return `
            <div class="col-md-4">
              <div class="card h-100" id="tournamentFinalPositionCard">
                <div class="card-header"><h6>${tt("ui.tournament.final_position", "Final Position")}</h6></div>
                <div class="card-body">
                  <div class="h5 mb-1">${s.final_position ?? "-"}</div>
                  <small class="text-muted">${tt("ui.tournament.after_final_game", "After final game")}</small>
                </div>
              </div>
            </div>`;
    }
    if (cardId === "summary_average") {
      return `
            <div class="col-md-4">
              <div class="card h-100">
                <div class="card-header"><h6>${tt("ui.tournament.average", "Average")}</h6></div>
                <div class="card-body">
                  <div class="h5 mb-1">${s.average ?? "-"}</div>
                  <small class="text-muted">${tt("ui.tournament.cumulated", "Cumulated")}</small>
                </div>
              </div>
            </div>`;
    }
    if (cardId === "summary_best_position") {
      return `
            <div class="col-md-4">
              <div class="card h-100">
                <div class="card-header"><h6>${tt("ui.tournament.best_position", "Best Position")}</h6></div>
                <div class="card-body">
                  <div class="h5 mb-1">${s.best_position ?? "-"}</div>
                  <small class="text-muted">${s.best_position_game ?? ""}</small>
                </div>
              </div>
            </div>`;
    }
    if (cardId === "best_highest_game") {
      return `
            <div class="col-md-4">
              <div class="card h-100">
                <div class="card-header"><h6>${tt("ui.tournament.highest_game", "Highest Game")}</h6></div>
                <div class="card-body">
                  <div class="h5 mb-1">${b.highest_game?.score ?? "-"}</div>
                  <small class="text-muted">${b.highest_game?.stage || ""} ${b.highest_game?.game ? `(G${b.highest_game.game})` : ""}</small>
                </div>
              </div>
            </div>`;
    }
    if (cardId === "best_highest_pair") {
      return `
            <div class="col-md-4">
              <div class="card h-100">
                <div class="card-header"><h6>${tt("ui.tournament.highest_pair", "Highest Pair")}</h6></div>
                <div class="card-body">
                  <div class="h5 mb-1">${b.highest_pair?.score ?? "-"}</div>
                  <small class="text-muted">${b.highest_pair?.stage || ""} ${b.highest_pair?.pair ? `(${b.highest_pair.pair})` : ""}</small>
                </div>
              </div>
            </div>`;
    }
    if (cardId === "handicap_profile") {
      return `
            <div class="col-md-4">
              <div class="card h-100">
                <div class="card-header"><h6>${tt("ui.tournament.player_handicap_card", "Handicap")}</h6></div>
                <div class="card-body">
                  <div class="h5 mb-1">${hp?.handicap_per_game != null ? hp.handicap_per_game : "—"}</div>
                  <small class="text-muted d-block">${tt("ui.tournament.apriori_avg_label", "a priori average")}: ${
                    hp?.a_priori_average != null ? hp.a_priori_average : "—"
                  }</small>
                  ${
                    hp?.handicap_reference != null
                      ? `<small class="text-muted d-block mt-1">${tt("ui.tournament.handicap_ref_label", "Reference")}: ${hp.handicap_reference}</small>`
                      : ""
                  }
                </div>
              </div>
            </div>`;
    }
    if (cardId === "best_highest_block") {
      return `
            <div class="col-md-4">
              <div class="card h-100">
                <div class="card-header"><h6>${tt("ui.tournament.highest_block", "Highest Block")}</h6></div>
                <div class="card-body">
                  <div class="h5 mb-1">${b.highest_block?.score ?? "-"}</div>
                  <small class="text-muted">${b.highest_block?.stage || ""}</small>
                </div>
              </div>
            </div>`;
    }
    return "";
  }

  function buildPlayerMetricRowsHtml(payload) {
    const layout =
      Array.isArray(payload.player_card_layout) && payload.player_card_layout.length > 0
        ? payload.player_card_layout
        : DEFAULT_PLAYER_CARD_LAYOUT;
    const rows = [];
    for (let i = 0; i < layout.length; i += 3) {
      rows.push(layout.slice(i, i + 3));
    }
    return rows
      .map((row, idx) => {
        const margin = idx === 0 ? "mb-3" : "mb-3 mt-8";
        return `<div class="row g-3 ${margin}">${row.map((cid) => buildPlayerMetricCardHtml(cid, payload)).join("")}</div>`;
      })
      .join("");
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
          ${buildPlayerMetricRowsHtml(payload)}
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
          <div id="tournamentPlayerKoBracketMount" class="tournament-player-ko-bracket-mount"></div>
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
    const koPlayerMount = document.getElementById("tournamentPlayerKoBracketMount");
    if (koPlayerMount) {
      koPlayerMount.innerHTML = renderKoBracketCard(payload.ko_bracket || { matches: [] });
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
      const path = `/tournament/get_available_seasons${tournamentParam}`;
      const data = await fetchJson(path);
      const list = Array.isArray(data) ? data : [];
      dbgTournamentStats("get_available_seasons", {
        fetchPath: path,
        fetchWithDatabase: withDatabase(path),
        tournamentFilter: tournament || null,
        count: list.length,
        seasons: list,
      });
      return list;
    } catch (err) {
      console.error("Failed to load seasons:", err);
      return [];
    }
  }

  async function getAvailableTournaments(season) {
    try {
      const path = `/tournament/get_available_tournaments?season=${encodeURIComponent(season)}`;
      const data = await fetchJson(path);
      const list = Array.isArray(data) ? data : [];
      dbgTournamentStats("get_available_tournaments", {
        fetchPath: path,
        fetchWithDatabase: withDatabase(path),
        season: season || null,
        count: list.length,
        tournaments: list,
      });
      return list;
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

  function _normPickToken(s) {
    const t = String(s ?? "").trim();
    if (!t) return "";
    try {
      return t.normalize("NFC");
    } catch (e) {
      return t;
    }
  }

  function pickValue(items, preferred) {
    if (!Array.isArray(items) || items.length === 0) return "";
    const wantRaw = preferred == null ? "" : String(preferred).trim();
    const want = _normPickToken(wantRaw);
    const rowVals = items.map((item) => String(item.value ?? item).trim());

    if (wantRaw) {
      const idxExact = rowVals.findIndex((v) => v === wantRaw);
      if (idxExact >= 0) return rowVals[idxExact];
      const idxTrim = rowVals.findIndex((v) => v.trim() === wantRaw);
      if (idxTrim >= 0) return rowVals[idxTrim];
      const low = wantRaw.toLowerCase();
      const idxCi = rowVals.findIndex((v) => v.toLowerCase() === low);
      if (idxCi >= 0) return rowVals[idxCi];
      if (want) {
        const idxNfc = rowVals.findIndex((v) => _normPickToken(v) === want);
        if (idxNfc >= 0) return rowVals[idxNfc];
      }
    }
    return rowVals[0] ?? "";
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
    currentTournamentGender = section.tournament_gender || null;
    renderCards(section.cards || []);
    const koOverview = document.getElementById("tournamentKoBracketOverview");
    if (koOverview) {
      koOverview.innerHTML = renderKoBracketCard(section.ko_bracket || { matches: [] });
    }

    const pqCard = document.getElementById("tournamentPostQualificationCard");
    const koRrCard = document.getElementById("tournamentKoFinaleRoundResultsCard");
    const hasPostQual =
      !String(currentFilters.round || "").trim() &&
      section.leaderboard_post_qualification &&
      Array.isArray(section.leaderboard_post_qualification.data) &&
      section.leaderboard_post_qualification.data.length > 0;
    if (pqCard) {
      if (hasPostQual) {
        pqCard.style.display = "";
        const h = document.getElementById("tournamentPostQualificationHeader");
        if (h) {
          h.textContent = tt("ui.tournament.leaderboard_post_qual", "Qualification — places after the cut");
        }
        renderTable("tournamentPostQualificationTable", section.leaderboard_post_qualification);
      } else {
        pqCard.style.display = "none";
        const pqEl = document.getElementById("tournamentPostQualificationTable");
        if (pqEl) pqEl.innerHTML = "";
      }
    }
    const hasKoRr =
      !String(currentFilters.round || "").trim() && section.round_results_ko && Array.isArray(section.round_results_ko.columns);
    if (koRrCard) {
      if (hasKoRr) {
        koRrCard.style.display = "";
        const kh = document.getElementById("tournamentKoFinaleRoundResultsHeader");
        if (kh) {
          kh.textContent = tt("ui.tournament.round_results_ko_title", "Knockout round — game results");
        }
        renderRoundResultsHeatmapControls("tournamentKoFinaleRoundResultsHeatmapControls");
        renderTable("tournamentKoFinaleRoundResultsTable", section.round_results_ko);
        currentRoundResultsHeatmapRange =
          section?.round_results_ko?.metadata?.heatmap_ranges?.game_score || DEFAULT_GAME_HEATMAP_RANGE;
        requestAnimationFrame(() => {
          requestAnimationFrame(() => scheduleRoundResultsHeatmapApply());
        });
        window.setTimeout(() => scheduleRoundResultsHeatmapApply(20, 150), 1200);
      } else {
        koRrCard.style.display = "none";
        const koTbl = document.getElementById("tournamentKoFinaleRoundResultsTable");
        if (koTbl) koTbl.innerHTML = "";
      }
    }
    lastOverviewHasPostQual = !!hasPostQual;
    lastOverviewHasKoRr = !!hasKoRr;

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
    enablePlayerCellNavigation("tournamentPostQualificationTable");
    enablePlayerCellNavigation("tournamentKoFinaleRoundResultsTable");
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
        label: String(r.round_number),
        title: (r.round_name && String(r.round_name).trim()) || `${tt("ui.tournament.round", "Round")} ${r.round_number}`,
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
    const preferredTournament = currentFilters.tournament;
    const season = currentFilters.season;
    const tournaments = await getAvailableTournaments(currentFilters.season);
    const tournamentItems = tournaments.map((name) => ({ value: name, label: name }));
    currentFilters.tournament = pickValue(tournamentItems, currentFilters.tournament);
    dbgTournamentStats("refresh_tournament_buttons", {
      season,
      preferredTournament,
      listCount: tournamentItems.length,
      tournaments,
      pickedTournament: currentFilters.tournament,
    });
    renderButtonGroup("tournamentNameButtons", tournamentItems, currentFilters.tournament, async (value) => {
      currentFilters.tournament = value || "";
      await refreshTournamentButtons();
      await refreshRoundButtons();
      await applyFiltersAndRender(true);
    });
    return preferredTournament === currentFilters.tournament;
  }

  async function refreshSeasonButtons() {
    const preferredSeason = currentFilters.season;
    const tournament = currentFilters.tournament;
    const seasons = await getAvailableSeasons(currentFilters.tournament);
    const seasonItems = seasons.map((s) => ({ value: String(s), label: String(s) }));
    currentFilters.season = pickValue(seasonItems, currentFilters.season);
    dbgTournamentStats("refresh_season_buttons", {
      tournamentFilter: tournament,
      preferredSeason,
      listCount: seasonItems.length,
      seasons,
      pickedSeason: currentFilters.season,
    });
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
    const rawSeasonParam = params.get("season");
    const deepLinkedPlayer = (params.get("player") || "").trim();
    currentFilters.tournament = params.get("tournament") || "";
    const seasons = await getAvailableSeasons(currentFilters.tournament);
    const seasonItems = seasons.map((s) => ({ value: String(s), label: String(s) }));
    const explicitSeason = normalizeSeasonFromUrl(rawSeasonParam, seasons);
    if (rawSeasonParam) {
      currentFilters.season = pickValue(seasonItems, explicitSeason);
    } else if (currentFilters.tournament && seasons.length > 0) {
      // Tournament-only deep links: pick the newest season that contains this event.
      currentFilters.season = String(seasons[seasons.length - 1]);
    } else {
      currentFilters.season = pickValue(seasonItems, "");
    }

    dbgTournamentStats("init:after_url_parse", {
      locationSearch: window.location.search,
      database: getCurrentDatabase(),
      rawSeasonParam,
      normalizedSeasonParam: explicitSeason,
      urlTournament: currentFilters.tournament,
      seasonsFromApi: seasons,
      chosenSeason: currentFilters.season,
    });

    await refreshSeasonButtons();

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
