const singleTeam = $("singleTeam");
const analyzeSingleBtn = $("analyzeSingleBtn");
const singleTeamError = $("singleTeamError");
const singleResults = $("singleResults");

function formatMoneyline(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${n > 0 ? "+" : ""}${Math.round(n)}`;
}

function formatWinChance(value) {
  const n = Number(value);
  return Number.isFinite(n) ? `${Math.round(n * 100)}%` : "—";
}

function teamTrendClass(history) {
  const recent = history?.recent_8 || {};
  const games = Number(recent.games || 0);
  const rate = Number(recent.cover_rate);
  if (games >= 6 && Number.isFinite(rate)) {
    if (rate >= 0.625) return "team-market-positive";
    if (rate <= 0.375) return "team-market-negative";
  }
  return "team-market-neutral";
}

function marketTrendText(market) {
  const history = market?.history || {};
  const recent = history.recent_8 || {};
  const role = history.same_role || {};
  const recentText = recent.summary || "No recent ATS record";
  const roleText = role.summary || "—";
  return `${recentText} • As ${history.role || "current role"}: ${roleText} • ${history.trend_label || "No strong ATS trend"}`;
}

function renderMarketTeamCard(teamAbbr, opponentAbbr, leading = false) {
  const team = state.data?.teams?.[teamAbbr];
  const context = actualGameContext(team, opponentAbbr);
  const market = context?.market || {};
  if (!team || !context || !market.available) return "";

  const chance = market.market_win_probability ?? market.raw_implied_win_probability;
  const trendClass = teamTrendClass(market.history);
  return `<div class="market-team-card ${leading ? "leading" : ""}">
    <div class="market-team-name">${team.name}</div>
    <div class="market-team-line">Spread ${signedLine(market.team_spread)} • ML ${formatMoneyline(market.moneyline)} • Total ${market.game_total ?? "—"}</div>
    <div class="market-win-chance"><strong>${formatWinChance(chance)}</strong><span>market win chance</span></div>
    <div class="market-team-detail">${market.chance_label || market.line_quality || "Market context available"}. Implied team points: ${market.implied_team_total ?? "—"}.</div>
    <div class="market-team-detail ${trendClass}">${marketTrendText(market)}</div>
  </div>`;
}

function renderMatchupMarketSummary(teamAbbrA, teamAbbrB) {
  const teamAData = state.data?.teams?.[teamAbbrA];
  const teamBData = state.data?.teams?.[teamAbbrB];
  const contextA = actualGameContext(teamAData, teamAbbrB);
  const contextB = actualGameContext(teamBData, teamAbbrA);

  if (!contextA || !contextB) {
    return `<div class="market-unavailable"><b>Vegas context:</b> these teams are not currently scheduled against each other in their next game, so current-week odds are not applied to this manual matchup. The season matchup analysis below still works normally.</div>`;
  }

  const marketA = contextA.market || {};
  const marketB = contextB.market || {};
  if (!marketA.available && !marketB.available) {
    return `<div class="market-unavailable"><b>Vegas context:</b> the matchup is scheduled, but current line data is not available yet.</div>`;
  }

  const chanceA = Number(marketA.market_win_probability ?? marketA.raw_implied_win_probability);
  const chanceB = Number(marketB.market_win_probability ?? marketB.raw_implied_win_probability);
  const leadA = Number.isFinite(chanceA) && (!Number.isFinite(chanceB) || chanceA > chanceB);
  const leadB = Number.isFinite(chanceB) && (!Number.isFinite(chanceA) || chanceB > chanceA);
  const week = contextA.week || contextB.week || "—";

  return `<section class="market-summary">
    <div class="market-summary-head">
      <div class="mini-eyebrow">VEGAS / MARKET OUTLOOK • WEEK ${week}</div>
      <h3>Current odds + team history</h3>
      <p>Moneyline chance is the no-vig implied probability when both sides of the market are available. ATS history is supporting context, not a guarantee.</p>
    </div>
    <div class="market-team-grid">
      ${renderMarketTeamCard(teamAbbrA, teamAbbrB, leadA)}
      ${renderMarketTeamCard(teamAbbrB, teamAbbrA, leadB)}
    </div>
  </section>`;
}

function initSingleTeamSelector() {
  if (!state.data) {
    window.setTimeout(initSingleTeamSelector, 80);
    return;
  }
  if (!singleTeam || singleTeam.options.length > 1) return;
  const entries = Object.entries(state.data.teams || {}).sort((a, b) => a[1].name.localeCompare(b[1].name));
  for (const [abbr, team] of entries) singleTeam.add(new Option(team.name, abbr));
}

function validateSingleTeam() {
  analyzeSingleBtn.disabled = !(state.data && singleTeam.value);
  singleTeamError.textContent = "";
}

singleTeam?.addEventListener("change", validateSingleTeam);

analyzeSingleBtn?.addEventListener("click", () => {
  singleTeamError.textContent = "";
  const abbr = singleTeam.value;
  const team = state.data?.teams?.[abbr];
  if (!team) return;
  const context = actualGameContext(team);
  if (!context?.opponent || !state.data?.teams?.[context.opponent]) {
    singleTeamError.textContent = "No upcoming matchup is available for that team yet. It may be on a bye or the next schedule context has not posted.";
    singleResults.classList.add("hidden");
    return;
  }

  const opponent = context.opponent;
  singleResults.innerHTML = `
    <h2 class="results-title">${team.name} Week ${context.week || "—"} <span>matchup</span></h2>
    ${renderMatchupMarketSummary(abbr, opponent)}
    ${directionCard(abbr, opponent)}
    ${directionCard(opponent, abbr)}
  `;
  singleResults.classList.remove("hidden");
  singleResults.scrollIntoView({ behavior: "smooth", block: "start" });
});

// Add a small, conservative team ATS signal to the existing game-market factor.
// This remains team/game context; it is not represented as player-prop history.
const matchupEdgeV2MarketMultiplier = marketMultiplier;
marketMultiplier = function(player, context) {
  let factor = matchupEdgeV2MarketMultiplier(player, context);
  const recent = context?.market?.history?.recent_8 || {};
  const games = Number(recent.games || 0);
  const rate = Number(recent.cover_rate);
  if (games >= 6 && Number.isFinite(rate)) {
    const historyAdjustment = clamp((rate - 0.5) * 0.08, -0.02, 0.02);
    factor *= (1 + historyAdjustment);
  }
  return clamp(factor, 0.86, 1.14);
};

marketReason = function(player, context) {
  const market = context?.market;
  if (!market?.available) return "";
  const mult = marketMultiplier(player, context);
  const delta = Math.round((mult - 1) * 100);
  const chance = market.market_win_probability ?? market.raw_implied_win_probability;
  const history = market.history || {};
  return ` Vegas: ${signedLine(market.team_spread)} spread, ML ${formatMoneyline(market.moneyline)}, ${formatWinChance(chance)} market win chance, ${market.game_total} total, ${market.implied_team_total} implied points; ${delta === 0 ? "neutral" : `${delta > 0 ? "+" : ""}${delta}%`} game-market adjustment. Team trend: ${history.recent_8?.summary || "—"} (${history.trend_label || "no strong ATS trend"}).`;
};

renderComparisonPlayer = function(analysis, leading) {
  const { entry, context, opponent, matchup, score } = analysis;
  if (!context || !opponent) {
    return `<div class="comparison-player ${leading ? "leading" : ""}">
      <h3>${entry.name} <span class="player-pos">${entry.position}</span></h3>
      <div class="comparison-sub">${entry.teamName}</div>
      <p class="empty">No upcoming game context is available for this player yet.</p>
    </div>`;
  }

  const weatherMult = weatherMultiplier(entry, context);
  const marketMult = marketMultiplier(entry, context);
  const weather = context.weather || {};
  const market = context.market || {};
  const injury = injurySummary(entry) || "No current designation";
  const weatherText = weather.available
    ? (weather.protected ? "Roof protected" : `${weather.temperature_f != null ? `${Math.round(weather.temperature_f)}°F, ` : ""}${weather.label || "forecast available"}`)
    : "Forecast unavailable";
  const chance = market.market_win_probability ?? market.raw_implied_win_probability;
  const marketText = market.available
    ? `${signedLine(market.team_spread)} spread, ML ${formatMoneyline(market.moneyline)}, ${formatWinChance(chance)} win chance, total ${market.game_total}, implied ${market.implied_team_total}`
    : "Line unavailable";
  const trendText = market.available ? marketTrendText(market) : "Team ATS trend unavailable";
  const trendClass = market.available ? teamTrendClass(market.history) : "team-market-neutral";

  return `<div class="comparison-player ${leading ? "leading" : ""}">
    <h3>${entry.name} <span class="player-pos">${entry.position}</span>${injuryBadge(entry)}</h3>
    <div class="comparison-sub">${entry.teamName} vs. ${opponent.name} • Week ${context.week || "—"}</div>
    <div class="start-score"><strong>${Math.round(score * 100)}</strong><span>Start score</span></div>
    <div class="factor-list">
      <div class="factor-row"><span>Matchup</span><span>${pct(matchup)}th percentile</span></div>
      <div class="factor-row"><span>Availability</span><span>${Math.round(playerAvailability(entry) * 100)}% • ${injury}</span></div>
      <div class="factor-row"><span>Weather</span><span class="${factorClass(weatherMult)}">${weatherText} • ${Math.round((weatherMult - 1) * 100)}%</span></div>
      <div class="factor-row"><span>Vegas</span><span class="${factorClass(marketMult)}">${marketText} • ${Math.round((marketMult - 1) * 100)}%</span></div>
      <div class="factor-row"><span>Team vs. market</span><span class="${trendClass}">${trendText}</span></div>
      <div class="factor-row"><span>Usage</span><span>${entry.position === "RB" ? `${share(entry.rush_share)} rush / ${share(entry.target_share)} targets` : entry.position === "QB" ? `${share(entry.pass_attempt_share)} pass attempts` : `${share(entry.target_share)} targets / ${share(entry.recent_target_share)} recent`}</span></div>
    </div>
  </div>`;
};

// The original Team vs Team listener renders first; this later listener inserts
// the market outlook immediately beneath the results title.
analyzeBtn.addEventListener("click", () => {
  const a = teamA.value;
  const b = teamB.value;
  if (!a || !b || a === b || !state.data) return;
  const title = results.querySelector(".results-title");
  if (title) title.insertAdjacentHTML("afterend", renderMatchupMarketSummary(a, b));
});

compareBtn.addEventListener("click", () => {
  if (compareResult.classList.contains("hidden") || compareResult.querySelector(".prop-source-note")) return;
  compareResult.insertAdjacentHTML(
    "beforeend",
    `<p class="prop-source-note">Vegas shown here is each player's <b>team/game market context</b> (spread, moneyline, total, implied scoring and team ATS history). nflverse does not provide player-specific prop lines, so Matchup Edge does not label a player as beating a prop unless a dedicated prop-odds feed is added.</p>`
  );
});

initSingleTeamSelector();
