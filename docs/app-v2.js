const state = { data: null, players: [] };
const $ = (id) => document.getElementById(id);

const weaknessLabels = {
  pass: "Passing defense",
  run: "Run defense",
  red_zone: "Red-zone defense",
  wr: "Wide receivers",
  te: "Tight ends",
  rb: "Running backs",
};

const teamA = $("teamA");
const teamB = $("teamB");
const analyzeBtn = $("analyzeBtn");
const results = $("results");
const error = $("formError");
const playerA = $("playerA");
const playerB = $("playerB");
const compareBtn = $("compareBtn");
const compareError = $("compareError");
const compareResult = $("compareResult");
const playerOptions = $("playerOptions");

fetch("data/matchups.json", { cache: "no-store" })
  .then((res) => {
    if (!res.ok) throw new Error("Current matchup data is not available yet.");
    return res.json();
  })
  .then((data) => {
    state.data = data;
    const entries = Object.entries(data.teams || {}).sort((a, b) => a[1].name.localeCompare(b[1].name));
    for (const [abbr, team] of entries) {
      teamA.add(new Option(team.name, abbr));
      teamB.add(new Option(team.name, abbr));
      for (const player of team.players || []) {
        if (!["QB", "RB", "WR", "TE"].includes(player.position)) continue;
        state.players.push({ ...player, teamAbbr: abbr, teamName: team.name });
      }
    }
    state.players.sort((a, b) => a.name.localeCompare(b.name));
    for (const player of state.players) {
      const option = document.createElement("option");
      option.value = player.name;
      option.label = `${player.teamName} • ${player.position}`;
      playerOptions.appendChild(option);
    }
    if (!entries.length) throw new Error("The data pipeline has not run yet. Run the Update NFL Data workflow once in GitHub Actions.");
    const when = data.meta?.generated_at ? new Date(data.meta.generated_at).toLocaleString() : "recently";
    const injuryWeek = data.meta?.injury_week ? ` • Injury report Week ${data.meta.injury_week}` : "";
    $("freshness").textContent = `NFL ${data.meta?.season ?? "current"} • Through Week ${data.meta?.through_week ?? "—"}${injuryWeek} • Updated ${when}`;
    validateCompare();
  })
  .catch((err) => {
    $("freshness").textContent = err.message;
    error.textContent = err.message;
    compareError.textContent = err.message;
  });

function validate() {
  const a = teamA.value;
  const b = teamB.value;
  analyzeBtn.disabled = !(a && b && a !== b && state.data);
  error.textContent = a && b && a === b ? "Choose two different teams." : "";
}
teamA.addEventListener("change", validate);
teamB.addEventListener("change", validate);

function validateCompare() {
  compareBtn.disabled = !(state.data && playerA.value.trim() && playerB.value.trim());
  if (!playerA.value.trim() || !playerB.value.trim()) compareError.textContent = "";
}
playerA.addEventListener("input", validateCompare);
playerB.addEventListener("input", validateCompare);

function pct(v) { return Math.round((Number(v) || 0) * 100); }
function share(v) { return `${Math.round((Number(v) || 0) * 100)}%`; }
function clamp(v, min = 0, max = 1) { return Math.max(min, Math.min(max, Number(v) || 0)); }
function defenseScores(defense) { return defense?.adjusted_scores || defense?.scores || {}; }
function signedLine(v) { const n = Number(v); return Number.isFinite(n) ? `${n > 0 ? "+" : ""}${n.toFixed(1)}` : "—"; }

function classifyWeaknesses(defense) {
  const scores = defenseScores(defense);
  const ranked = Object.entries(scores)
    .filter(([key]) => weaknessLabels[key])
    .map(([key, score]) => ({ key, score: Number(score) || 0 }))
    .sort((a, b) => b.score - a.score);

  const major = ranked.filter(x => x.score >= 0.75).slice(0, 2);
  const minor = ranked
    .filter(x => x.score >= 0.60 && x.score < 0.75 && !major.some(m => m.key === x.key))
    .slice(0, 2);
  return { major, minor };
}

function injuryDelta(key, defense) {
  const base = Number(defense?.scores?.[key] || 0);
  const adjusted = Number(defense?.adjusted_scores?.[key] ?? base);
  return Math.max(0, adjusted - base);
}

function injuryAdjustmentText(item, defense) {
  const delta = injuryDelta(item.key, defense);
  return delta >= 0.01 ? ` Current defensive injuries add about ${Math.round(delta * 100)} vulnerability points.` : "";
}

function weaknessDetail(item, defense) {
  const s = defense?.stats || {};
  const percentile = pct(item.score);
  const injuryText = injuryAdjustmentText(item, defense);
  switch (item.key) {
    case "pass": return `${percentile}th-percentile vulnerability. ${s.pass_yards_per_play ?? "—"} pass yards/play allowed; ${Math.round((s.explosive_pass_rate || 0) * 100)}% explosive-pass rate.${injuryText}`;
    case "run": return `${percentile}th-percentile vulnerability. ${s.rush_yards_per_play ?? "—"} rush yards/play allowed; ${Math.round((s.explosive_run_rate || 0) * 100)}% explosive-run rate.${injuryText}`;
    case "red_zone": return `${percentile}th-percentile vulnerability based on opponent touchdown rate inside the 20.${injuryText}`;
    case "wr": return `${percentile}th-percentile vulnerability to WR production; ${s.ppr_allowed_per_game?.WR ?? "—"} PPR points/game allowed to wide receivers.${injuryText}`;
    case "te": return `${percentile}th-percentile vulnerability to TE production; ${s.ppr_allowed_per_game?.TE ?? "—"} PPR points/game allowed to tight ends.${injuryText}`;
    case "rb": return `${percentile}th-percentile vulnerability to RB production; ${s.ppr_allowed_per_game?.RB ?? "—"} PPR points/game allowed to running backs.${injuryText}`;
    default: return `${percentile}th-percentile vulnerability.${injuryText}`;
  }
}

function playerAvailability(player) {
  return clamp(player?.injury?.availability ?? 1);
}

function playerMatchupScore(player, defense) {
  const scores = defenseScores(defense);
  if (player.position === "QB") return Number(scores.pass || 0.5);
  if (player.position === "RB") return Math.max(Number(scores.run || 0.5), Number(scores.rb || 0.5), Number(scores.red_zone || 0.5) * 0.85);
  if (player.position === "WR") return Math.max(Number(scores.pass || 0.5), Number(scores.wr || 0.5));
  if (player.position === "TE") return Math.max(Number(scores.pass || 0.5), Number(scores.te || 0.5));
  return 0.5;
}

function actualGameContext(offense, defenseAbbr = null) {
  const context = offense?.week_context || {};
  if (!context?.opponent) return null;
  if (defenseAbbr && context.opponent !== defenseAbbr) return null;
  return context;
}

function weatherMultiplier(player, context) {
  if (!context?.weather?.available) return 1;
  return Number(context.weather?.multipliers?.[player.position] ?? 1) || 1;
}

function marketMultiplier(player, context) {
  const market = context?.market;
  if (!market?.available) return 1;
  const implied = Number(market.implied_team_total);
  const total = Number(market.game_total);
  const line = Number(market.team_spread);
  let factor = 1;
  if (Number.isFinite(implied)) factor += clamp((implied - 22.5) * 0.012, -0.07, 0.08);
  if (Number.isFinite(total)) {
    if (total >= 50) factor += 0.02;
    if (total <= 40) factor -= 0.025;
  }
  if (Number.isFinite(line)) {
    if (player.position === "RB" && line <= -5) factor += 0.03;
    if (["QB", "WR", "TE"].includes(player.position) && line >= 5) factor += 0.02;
    if (["QB", "WR", "TE"].includes(player.position) && line <= -10) factor -= 0.015;
  }
  return clamp(factor, 0.88, 1.12);
}

function playerFit(player, offense, defense, context = null) {
  const matchup = playerMatchupScore(player, defense);
  const roleScore = Number(player.effective_role_score ?? player.role_score) || 0;
  const role = Math.min(1, roleScore / 0.62);
  let fit = 0.45 * role + 0.55 * matchup;
  fit *= playerAvailability(player);

  const olPenalty = Number(offense?.injuries?.offensive_line_penalty || 0);
  const olWeight = player.position === "RB" || player.position === "QB" ? 0.9 : 0.5;
  fit *= (1 - olPenalty * olWeight);
  fit *= weatherMultiplier(player, context);
  fit *= marketMultiplier(player, context);
  return clamp(fit);
}

function injurySummary(player) {
  const injury = player?.injury || {};
  const label = injury.label || "";
  if (!label) return "";
  const issue = injury.primary_injury ? ` • ${injury.primary_injury}` : "";
  return `${label}${issue}`;
}

function weatherReason(player, context) {
  const weather = context?.weather;
  if (!weather?.available) return "";
  const mult = weatherMultiplier(player, context);
  if (weather.protected) return " Weather: roof-protected, no adjustment.";
  const parts = [];
  if (weather.temperature_f != null) parts.push(`${Math.round(weather.temperature_f)}°F`);
  if (weather.wind_mph != null) parts.push(`${Math.round(weather.wind_mph)} mph wind`);
  if (weather.precip_probability != null) parts.push(`${Math.round(weather.precip_probability)}% precip`);
  const delta = Math.round((mult - 1) * 100);
  return ` Weather: ${parts.join(", ") || weather.label}; ${delta === 0 ? "neutral" : `${delta > 0 ? "+" : ""}${delta}%`} position adjustment.`;
}

function marketReason(player, context) {
  const market = context?.market;
  if (!market?.available) return "";
  const mult = marketMultiplier(player, context);
  const delta = Math.round((mult - 1) * 100);
  return ` Vegas: ${signedLine(market.team_spread)} team line, ${market.game_total} total, ${market.implied_team_total} implied points; ${delta === 0 ? "neutral" : `${delta > 0 ? "+" : ""}${delta}%`} scoring-environment adjustment.`;
}

function playerReason(player, offense, defense, context = null) {
  const s = defenseScores(defense);
  const injury = injurySummary(player);
  const injuryText = injury ? ` Status: ${injury}.` : "";
  const boost = Number(player.injury_role_boost || 0);
  const boostText = boost >= 0.025 ? ` Teammate injuries increase projected opportunity.` : "";
  const olPenalty = Number(offense?.injuries?.offensive_line_penalty || 0);
  const lineText = olPenalty >= 0.025 && ["QB", "RB"].includes(player.position) ? ` Offensive-line injuries slightly lower confidence.` : "";
  const envText = `${weatherReason(player, context)}${marketReason(player, context)}`;

  if (player.position === "QB") {
    return `${share(player.pass_attempt_share)} of team pass attempts. Opponent pass-defense vulnerability: ${pct(s.pass)}th percentile.${injuryText}${lineText}${envText}`;
  }
  if (player.position === "RB") {
    const matchup = Math.max(Number(s.run || 0), Number(s.rb || 0));
    return `${share(player.rush_share)} rush share, ${share(player.target_share)} target share. RB/run matchup vulnerability: ${pct(matchup)}th percentile.${injuryText}${boostText}${lineText}${envText}`;
  }
  const posScore = player.position === "TE" ? s.te : s.wr;
  return `${share(player.target_share)} season target share, ${share(player.recent_target_share)} over the last four games. ${player.position} matchup vulnerability: ${pct(posScore)}th percentile.${injuryText}${boostText}${envText}`;
}

function likelyPlayers(offense, defense, context = null) {
  return (offense?.players || [])
    .map(p => ({ ...p, matchup: playerMatchupScore(p, defense), fit: playerFit(p, offense, defense, context) }))
    .filter(p => playerAvailability(p) > 0.25 && p.matchup >= 0.60 && p.fit >= 0.40)
    .sort((a, b) => b.fit - a.fit)
    .slice(0, 4);
}

function confidence(fit) {
  if (fit >= 0.76) return "HIGH";
  if (fit >= 0.59) return "MEDIUM";
  return "WATCH";
}

function statusClass(label = "") {
  const x = label.toUpperCase();
  if (x.includes("OUT") || x.includes("IR") || x.includes("RESERVE") || x.includes("PUP") || x.includes("SUSP")) return "out";
  if (x.includes("DOUBT")) return "doubtful";
  if (x.includes("QUESTION")) return "questionable";
  return "practice";
}

function injuryBadge(player) {
  const label = player?.injury?.label || "";
  return label ? `<span class="injury-badge ${statusClass(label)}">${label}</span>` : "";
}

function renderWeakness(item, level, defense) {
  return `<div class="weakness">
    <div class="weakness-top">
      <div class="weakness-name">${weaknessLabels[item.key]}</div>
      <span class="badge ${level}">${level.toUpperCase()}</span>
    </div>
    <div class="scorebar"><i style="width:${Math.max(4, pct(item.score))}%"></i></div>
    <p>${weaknessDetail(item, defense)}</p>
  </div>`;
}

function compactInjury(item) {
  const issue = item.primary_injury ? ` (${item.primary_injury})` : "";
  return `<span class="injury-chip ${statusClass(item.label)}"><b>${item.name}</b> ${item.position} • ${item.label}${issue}</span>`;
}

function renderInjuryContext(offense, defenseTeam) {
  const offenseItems = (offense?.injuries?.offense || []).slice(0, 5);
  const defenseItems = (defenseTeam?.injuries?.defense || []).slice(0, 5);
  if (!offenseItems.length && !defenseItems.length) {
    return `<div class="injury-context clear"><b>Injury check:</b> no material current injury adjustment found for this direction.</div>`;
  }
  const offenseHtml = offenseItems.length ? `<div><b>${offense.name} offense:</b> ${offenseItems.map(compactInjury).join(" ")}</div>` : "";
  const defenseHtml = defenseItems.length ? `<div><b>${defenseTeam.name} defense:</b> ${defenseItems.map(compactInjury).join(" ")}</div>` : "";
  return `<div class="injury-context"><div class="injury-context-title">INJURY-AWARE MATCHUP</div>${offenseHtml}${defenseHtml}</div>`;
}

function renderGameContext(offense, defenseAbbr) {
  const context = actualGameContext(offense, defenseAbbr);
  if (!context) return "";
  const weather = context.weather || {};
  const market = context.market || {};

  let weatherMain = weather.label || "Weather forecast unavailable";
  let weatherDetail = "Forecast will be added automatically when available.";
  if (weather.available && weather.protected) {
    weatherDetail = `${context.roof || "roof"} conditions protect this game from weather.`;
  } else if (weather.available) {
    const bits = [];
    if (weather.temperature_f != null) bits.push(`${Math.round(weather.temperature_f)}°F`);
    if (weather.wind_mph != null) bits.push(`${Math.round(weather.wind_mph)} mph wind`);
    if (weather.wind_gust_mph != null) bits.push(`gusts ${Math.round(weather.wind_gust_mph)} mph`);
    if (weather.precip_probability != null) bits.push(`${Math.round(weather.precip_probability)}% precipitation`);
    weatherDetail = bits.join(" • ");
  }

  let marketMain = market.label || "Vegas line unavailable";
  let marketDetail = "Current line data will appear when nflverse has it.";
  let trend = "";
  if (market.available) {
    marketMain = `${signedLine(market.team_spread)} • Total ${market.game_total} • Implied ${market.implied_team_total}`;
    const history = market.history || {};
    const recent = history.recent_8 || {};
    const role = history.same_role || {};
    marketDetail = `${market.line_quality}. Last 8: ${recent.summary || "—"}. As ${history.role || "current role"}: ${role.summary || "—"}.`;
    trend = `<span class="context-trend">${history.trend_label || "No strong ATS trend"}</span>`;
  }

  return `<div class="game-context">
    <div class="context-box weather">
      <div class="context-title">WEATHER • WEEK ${context.week || "—"}</div>
      <div class="context-main">${weatherMain}</div>
      <div class="context-detail">${weatherDetail}</div>
    </div>
    <div class="context-box market">
      <div class="context-title">VEGAS / MARKET CONTEXT</div>
      <div class="context-main">${marketMain}</div>
      <div class="context-detail">${marketDetail}</div>
      ${trend}
    </div>
  </div>`;
}

function directionCard(offenseAbbr, defenseAbbr) {
  const offense = state.data.teams[offenseAbbr];
  const defenseTeam = state.data.teams[defenseAbbr];
  const defense = defenseTeam.defense;
  const context = actualGameContext(offense, defenseAbbr);
  const weaknesses = classifyWeaknesses(defense);
  const players = likelyPlayers(offense, defense, context);
  const weaknessHtml = [
    ...weaknesses.major.map(x => renderWeakness(x, "major", defense)),
    ...weaknesses.minor.map(x => renderWeakness(x, "minor", defense)),
  ].join("") || `<p class="empty">No clear defensive weakness is showing at the 60th percentile or higher right now.</p>`;

  const playersHtml = players.map(p => `<div class="player">
    <div class="player-top">
      <div class="player-identity"><span class="player-name">${p.name}</span><span class="player-pos">${p.position}</span>${injuryBadge(p)}</div>
      <span class="confidence">${confidence(p.fit)}</span>
    </div>
    <p>${playerReason(p, offense, defense, context)}</p>
  </div>`).join("") || `<p class="empty">No healthy player clears both the usage and matchup thresholds with the current information.</p>`;

  return `<article class="direction">
    <div class="direction-head">
      <h2><b>${offense.name}</b> offense vs. ${defenseTeam.name} defense</h2>
      <span class="direction-tag">${defense.games || 0} games analyzed</span>
    </div>
    ${renderGameContext(offense, defenseAbbr)}
    ${renderInjuryContext(offense, defenseTeam)}
    <div class="grid">
      <div class="card">
        <h3>Defensive weaknesses</h3>
        <div class="weakness-list">${weaknessHtml}</div>
      </div>
      <div class="card">
        <h3>Players most likely to exploit them</h3>
        <div class="player-list">${playersHtml}</div>
      </div>
    </div>
  </article>`;
}

function resolvePlayer(value) {
  const query = value.trim().toLowerCase();
  if (!query) return null;
  const exact = state.players.filter(p => p.name.toLowerCase() === query);
  if (exact.length === 1) return exact[0];
  const starts = state.players.filter(p => p.name.toLowerCase().startsWith(query));
  if (starts.length === 1) return starts[0];
  const contains = state.players.filter(p => p.name.toLowerCase().includes(query));
  return contains.length === 1 ? contains[0] : null;
}

function weeklyPlayerAnalysis(entry) {
  const offense = state.data.teams[entry.teamAbbr];
  const context = actualGameContext(offense);
  if (!context) return { entry, offense, context: null, score: 0, matchup: 0.5, defense: null };
  const opponent = state.data.teams[context.opponent];
  if (!opponent) return { entry, offense, context, score: 0, matchup: 0.5, defense: null };
  const defense = opponent.defense;
  return {
    entry,
    offense,
    context,
    defense,
    opponent,
    matchup: playerMatchupScore(entry, defense),
    score: playerFit(entry, offense, defense, context),
  };
}

function factorClass(mult) {
  if (mult > 1.015) return "factor-positive";
  if (mult < 0.985) return "factor-negative";
  return "factor-neutral";
}

function renderComparisonPlayer(analysis, leading) {
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
  const weatherText = weather.available ? (weather.protected ? "Roof protected" : `${weather.temperature_f != null ? `${Math.round(weather.temperature_f)}°F, ` : ""}${weather.label || "forecast available"}`) : "Forecast unavailable";
  const marketText = market.available ? `${signedLine(market.team_spread)}, total ${market.game_total}, implied ${market.implied_team_total}` : "Line unavailable";
  return `<div class="comparison-player ${leading ? "leading" : ""}">
    <h3>${entry.name} <span class="player-pos">${entry.position}</span>${injuryBadge(entry)}</h3>
    <div class="comparison-sub">${entry.teamName} vs. ${opponent.name} • Week ${context.week || "—"}</div>
    <div class="start-score"><strong>${Math.round(score * 100)}</strong><span>Start score</span></div>
    <div class="factor-list">
      <div class="factor-row"><span>Matchup</span><span>${pct(matchup)}th percentile</span></div>
      <div class="factor-row"><span>Availability</span><span>${Math.round(playerAvailability(entry) * 100)}% • ${injury}</span></div>
      <div class="factor-row"><span>Weather</span><span class="${factorClass(weatherMult)}">${weatherText} • ${Math.round((weatherMult - 1) * 100)}%</span></div>
      <div class="factor-row"><span>Vegas</span><span class="${factorClass(marketMult)}">${marketText} • ${Math.round((marketMult - 1) * 100)}%</span></div>
      <div class="factor-row"><span>Usage</span><span>${entry.position === "RB" ? `${share(entry.rush_share)} rush / ${share(entry.target_share)} targets` : entry.position === "QB" ? `${share(entry.pass_attempt_share)} pass attempts` : `${share(entry.target_share)} targets / ${share(entry.recent_target_share)} recent`}</span></div>
    </div>
  </div>`;
}

function comparePlayers() {
  compareError.textContent = "";
  const a = resolvePlayer(playerA.value);
  const b = resolvePlayer(playerB.value);
  if (!a || !b) {
    compareError.textContent = "Choose two players from the player suggestions so I can match them to their teams.";
    compareResult.classList.add("hidden");
    return;
  }
  if (a.id === b.id) {
    compareError.textContent = "Choose two different players.";
    compareResult.classList.add("hidden");
    return;
  }

  const first = weeklyPlayerAnalysis(a);
  const second = weeklyPlayerAnalysis(b);
  let winner = first;
  if (second.score > first.score) winner = second;
  const diff = Math.abs(first.score - second.score);
  const tie = diff < 0.015;
  const winnerText = tie ? "TOO CLOSE TO CALL" : `START ${winner.entry.name.toUpperCase()}`;
  const reason = tie
    ? `${a.name} and ${b.name} are within two Start Score points, so this is essentially a toss-up with the current data.`
    : `${winner.entry.name} has the stronger combined weekly profile by ${Math.max(1, Math.round(diff * 100))} Start Score point${Math.round(diff * 100) === 1 ? "" : "s"}.`;
  const weeksDiffer = first.context && second.context && first.context.week !== second.context.week;

  compareResult.innerHTML = `
    <div class="winner-banner">
      <span class="winner-label">MATCHUP EDGE VERDICT</span>
      <strong>${winnerText}</strong>
      <p>${reason}</p>
    </div>
    <div class="comparison-grid">
      ${renderComparisonPlayer(first, !tie && winner.entry.id === first.entry.id)}
      ${renderComparisonPlayer(second, !tie && winner.entry.id === second.entry.id)}
    </div>
    ${weeksDiffer ? `<p class="week-note">These players currently have different next-game weeks, so this compares each player's next scheduled game rather than the same NFL week.</p>` : ""}
  `;
  compareResult.classList.remove("hidden");
  compareResult.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

compareBtn.addEventListener("click", comparePlayers);

analyzeBtn.addEventListener("click", () => {
  const a = teamA.value;
  const b = teamB.value;
  if (!a || !b || a === b || !state.data) return validate();
  results.innerHTML = `
    <h2 class="results-title">Matchup <span>breakdown</span></h2>
    ${directionCard(a, b)}
    ${directionCard(b, a)}
  `;
  results.classList.remove("hidden");
  results.scrollIntoView({ behavior: "smooth", block: "start" });
});
