const soloPlayer = $("soloPlayer");
const analyzeSoloPlayerBtn = $("analyzeSoloPlayerBtn");
const soloPlayerError = $("soloPlayerError");
const soloPlayerResult = $("soloPlayerResult");

function validateSoloPlayer() {
  if (!analyzeSoloPlayerBtn) return;
  analyzeSoloPlayerBtn.disabled = !(state.data && soloPlayer?.value.trim());
  if (soloPlayerError && !soloPlayer?.value.trim()) soloPlayerError.textContent = "";
}

function soloStatLine(game, position) {
  if (!game) return "";
  if (position === "QB") {
    return `${game.passing_yards ?? 0} pass yds • ${game.passing_tds ?? 0} pass TD • ${game.passing_interceptions ?? 0} INT • ${game.rushing_yards ?? 0} rush yds`;
  }
  if (position === "RB") {
    return `${game.rushing_attempts ?? 0} carries • ${game.rushing_yards ?? 0} rush yds • ${game.rushing_tds ?? 0} rush TD • ${game.receiving_receptions ?? 0} rec • ${game.receiving_yards ?? 0} rec yds`;
  }
  return `${game.receiving_receptions ?? 0} rec • ${game.receiving_yards ?? 0} rec yds • ${game.receiving_tds ?? 0} rec TD`;
}

function renderSoloGameRows(games, player, emptyText) {
  if (!games?.length) return `<p class="empty">${emptyText}</p>`;
  return `<div class="solo-game-list">${games.map(game => `
    <div class="solo-game-row">
      <div class="solo-game-meta"><strong>${game.season} W${game.week}</strong><span>${game.team} vs. ${game.opponent}</span></div>
      <div class="solo-game-ppr"><strong>${game.fantasy_points_ppr ?? "—"}</strong><span>PPR</span></div>
      <div class="solo-game-stats">${soloStatLine(game, player.position)}</div>
    </div>`).join("")}</div>`;
}

function renderSoloProps(player) {
  const props = Object.values(player?.props || {});
  if (!props.length) {
    return `<p class="empty">Current player prop lines are not posted for this player yet.</p>`;
  }
  const opponent = player?.matchup_history?.opponent || "opponent";
  return `<div class="solo-prop-grid">${props.map(prop => {
    const trend = prop.trend || {};
    const range = prop.line_min !== prop.line_max ? `${prop.line_min}–${prop.line_max}` : `${prop.consensus_line}`;
    return `<div class="solo-prop-card">
      <div class="solo-prop-top"><strong>${prop.label}</strong><span>${prop.consensus_line} consensus</span></div>
      <div class="solo-prop-detail">${prop.book_count || 0} book${prop.book_count === 1 ? "" : "s"} • posted range ${range}</div>
      <div class="solo-prop-detail">Recent: ${lineTrendText(trend.recent)}</div>
      <div class="solo-prop-detail">Vs ${opponent}: ${lineTrendText(trend.vs_opponent)}</div>
      <div class="solo-prop-trend ${historyTone(trend.label)}">${trend.label || "No strong prop trend"}</div>
    </div>`;
  }).join("")}</div>`;
}

function relevantDefenseKeys(position) {
  if (position === "QB") return ["pass", "red_zone"];
  if (position === "RB") return ["run", "rb", "red_zone"];
  if (position === "WR") return ["pass", "wr", "red_zone"];
  if (position === "TE") return ["pass", "te", "red_zone"];
  return [];
}

function renderSoloDefense(player, defense) {
  const scores = defenseScores(defense);
  const rows = relevantDefenseKeys(player.position).map(key => {
    const score = Number(scores[key] ?? 0.5);
    return `<div class="solo-defense-row">
      <div><strong>${weaknessLabels[key] || key}</strong><span>${pct(score)}th percentile vulnerability</span></div>
      <p>${weaknessDetail({ key, score }, defense)}</p>
    </div>`;
  });
  return rows.join("") || `<p class="empty">No position-specific defensive metrics are available.</p>`;
}

function renderSoloPlayerReport(analysis) {
  const { entry, offense, context, opponent, defense, score, matchup } = analysis;
  if (!context || !opponent || !defense) {
    return `<div class="solo-player-empty"><h3>${entry.name}</h3><p>No upcoming matchup is available for this player yet. The team may be on a bye or the next schedule context has not posted.</p></div>`;
  }

  const history = entry.matchup_history || {};
  const recentGames = [...(history.recent_games || [])].slice(-8).reverse();
  const opponentGames = [...(history.vs_opponent_games || [])].slice(-7).reverse();
  const outlook = confidence(score);

  return `
    <div class="solo-player-title">
      <div>
        <div class="mini-eyebrow">PLAYER • WEEK ${context.week || "—"}</div>
        <h2>${entry.name} <span>${entry.position}</span>${injuryBadge(entry)}</h2>
        <p>${entry.teamName} vs. ${opponent.name}</p>
      </div>
      <div class="solo-score"><strong>${Math.round(score * 100)}</strong><span>Start score</span><em>${outlook}</em></div>
    </div>

    <div class="solo-summary-card">
      <h3>Weekly outlook</h3>
      <p>${playerReason(entry, offense, defense, context)}</p>
      <div class="solo-summary-chips">
        <span>${pct(matchup)}th percentile matchup</span>
        <span>${Math.round(playerAvailability(entry) * 100)}% availability</span>
        <span>${outlook} weekly confidence</span>
      </div>
    </div>

    ${renderComparisonPlayer(analysis, false)}
    ${renderGameContext(offense, context.opponent)}
    ${renderInjuryContext(offense, opponent)}

    <section class="solo-section">
      <div class="solo-section-head"><div class="mini-eyebrow">OPPONENT DEFENSE</div><h3>${entry.position} matchup details</h3></div>
      <div class="solo-defense-list">${renderSoloDefense(entry, defense)}</div>
    </section>

    <section class="solo-section">
      <div class="solo-section-head"><div class="mini-eyebrow">CURRENT PLAYER MARKETS</div><h3>Multi-book prop lines + hit trends</h3></div>
      ${renderSoloProps(entry)}
      <p class="solo-footnote">Prop hit rates compare the player's actual results with today's consensus line. They are not a record against each historical game's original closing line.</p>
    </section>

    <section class="solo-section">
      <div class="solo-section-head"><div class="mini-eyebrow">RECENT FORM</div><h3>Last ${recentGames.length || 0} games</h3></div>
      ${renderSoloGameRows(recentGames, entry, "No recent player-game history is available.")}
    </section>

    <section class="solo-section">
      <div class="solo-section-head"><div class="mini-eyebrow">PLAYER VS. OPPONENT</div><h3>${history.summary?.trend_label || "Matchup-specific history"}</h3><p>${historyDisplay(entry)}</p></div>
      ${renderSoloGameRows(opponentGames, entry, "No prior games against this opponent are available.")}
    </section>

    ${renderHeadToHeadSummary(entry.teamAbbr, context.opponent)}
  `;
}

function analyzeSoloPlayer() {
  if (!soloPlayerError || !soloPlayerResult) return;
  soloPlayerError.textContent = "";
  const entry = resolvePlayer(soloPlayer.value);
  if (!entry) {
    soloPlayerError.textContent = "Choose a player from the suggestions so I can match them to the correct NFL team.";
    soloPlayerResult.classList.add("hidden");
    return;
  }

  const analysis = weeklyPlayerAnalysis(entry);
  soloPlayerResult.innerHTML = renderSoloPlayerReport(analysis);
  soloPlayerResult.classList.remove("hidden");
  soloPlayerResult.scrollIntoView({ behavior: "smooth", block: "start" });
}

soloPlayer?.addEventListener("input", validateSoloPlayer);
analyzeSoloPlayerBtn?.addEventListener("click", analyzeSoloPlayer);

// app-v2 loads the dataset asynchronously. Enable the one-player tool once that
// shared dataset has arrived, without creating a second fetch or scoring model.
(function waitForSoloData() {
  validateSoloPlayer();
  if (!state.data) window.setTimeout(waitForSoloData, 100);
})();
