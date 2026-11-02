function h2hKey(a, b) {
  return [a, b].sort().join("|");
}

function historyTone(label = "") {
  const text = label.toLowerCase();
  if (text.includes("strong") || text.includes("above baseline") || text.includes("clearing")) return "history-positive";
  if (text.includes("struggled") || text.includes("below baseline") || text.includes("weak") || text.includes("under trend")) return "history-negative";
  if (text.includes("outlier") || text.includes("one-game") || text.includes("small")) return "history-warning";
  return "history-neutral";
}

function signedNumber(value, digits = 1) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(digits)}`;
}

function renderH2HTeam(teamAbbr, pair) {
  const summary = pair?.summary?.[teamAbbr] || {};
  const team = state.data?.teams?.[teamAbbr];
  const record = `${summary.wins || 0}-${summary.losses || 0}${summary.ties ? `-${summary.ties}` : ""}`;
  const ats = summary.ats_games ? `${summary.ats_covers}-${summary.ats_losses}-${summary.ats_pushes} ATS` : "ATS unavailable";
  const outlier = summary.high_scoring_outliers ? ` • ${summary.high_scoring_outliers} high-scoring outlier${summary.high_scoring_outliers > 1 ? "s" : ""} detected` : "";
  return `<div class="h2h-team">
    <div class="h2h-team-name">${team?.name || teamAbbr}</div>
    <div class="h2h-record"><strong>${record}</strong><span>last ${summary.games || 0} meetings</span></div>
    <div class="h2h-detail">Avg points ${summary.avg_points_for ?? "—"} • Avg margin ${signedNumber(summary.avg_margin)} • ${ats}${outlier}</div>
    <div class="h2h-trend ${historyTone(summary.trend_label)}">${summary.trend_label || "No strong head-to-head trend"}</div>
  </div>`;
}

function renderH2HGame(game) {
  const away = game.away_team;
  const home = game.home_team;
  return `<span class="h2h-game">${game.season} W${game.week}: ${away} ${game.away_score}–${game.home_score} ${home}</span>`;
}

function renderHeadToHeadSummary(teamAAbbr, teamBAbbr) {
  const pair = state.data?.head_to_head?.[h2hKey(teamAAbbr, teamBAbbr)];
  if (!pair?.games?.length) {
    return `<section class="h2h-summary"><div class="h2h-head"><div class="mini-eyebrow">MATCHUP HISTORY</div><h3>No recent head-to-head sample</h3><p>The current-season matchup model still works normally; no historical trend is being forced into the recommendation.</p></div></section>`;
  }
  const games = [...pair.games].reverse();
  return `<section class="h2h-summary">
    <div class="h2h-head">
      <div class="mini-eyebrow">MATCHUP HISTORY • LAST ${pair.games.length} MEETINGS</div>
      <h3>Head-to-head trend + outlier check</h3>
      <p>Recent meetings are shown separately from the current-season model. One unusual shootout or blowout is flagged instead of being treated as a repeatable matchup edge.</p>
    </div>
    <div class="h2h-grid">
      ${renderH2HTeam(teamAAbbr, pair)}
      ${renderH2HTeam(teamBAbbr, pair)}
    </div>
    <div class="h2h-games">${games.map(renderH2HGame).join("")}</div>
  </section>`;
}

const matchupEdgeV3MarketSummary = renderMatchupMarketSummary;
renderMatchupMarketSummary = function(teamAAbbr, teamBAbbr) {
  return `${matchupEdgeV3MarketSummary(teamAAbbr, teamBAbbr)}${renderHeadToHeadSummary(teamAAbbr, teamBAbbr)}`;
};

function playerHistorySummary(player) {
  return player?.matchup_history?.summary || {};
}

function historyDisplay(player) {
  const history = player?.matchup_history || {};
  const summary = history.summary || {};
  if (!summary.games) return "No prior games vs this opponent";
  const baseline = summary.baseline_recent_ppr != null ? ` vs ${summary.baseline_recent_ppr} recent baseline` : "";
  const outlier = summary.high_outliers ? ` • ${summary.high_outliers} spike game${summary.high_outliers > 1 ? "s" : ""} filtered` : "";
  return `${summary.games} game${summary.games > 1 ? "s" : ""} • ${summary.adjusted_avg_ppr ?? summary.avg_ppr} avg PPR${baseline} • ${summary.trend_label}${outlier}`;
}

function primaryProp(player) {
  const props = player?.props || {};
  const preferred = {
    QB: ["passing_yards", "passing_touchdowns", "passing_completions", "passing_attempts"],
    RB: ["rushing_yards", "receiving_yards", "receiving_receptions", "touchdowns"],
    WR: ["receiving_yards", "receiving_receptions", "touchdowns"],
    TE: ["receiving_yards", "receiving_receptions", "touchdowns"],
  }[player?.position] || Object.keys(props);
  for (const key of preferred) if (props[key]) return props[key];
  return Object.values(props)[0] || null;
}

function lineTrendText(bucket) {
  if (!bucket?.games) return "no sample";
  const rate = bucket.over_rate == null ? "—" : `${Math.round(bucket.over_rate * 100)}%`;
  return `${bucket.overs}/${bucket.games} over (${rate})`;
}

function propDisplay(player) {
  const prop = primaryProp(player);
  if (!prop) return "";
  const trend = prop.trend || {};
  const opponent = player?.matchup_history?.opponent;
  const range = prop.line_min !== prop.line_max ? ` • books ${prop.line_min}–${prop.line_max}` : "";
  const matchup = trend.vs_opponent?.games ? ` • vs ${opponent}: ${lineTrendText(trend.vs_opponent)}` : "";
  return `${prop.label} ${prop.consensus_line} consensus (${prop.book_count} books)${range} • recent: ${lineTrendText(trend.recent)}${matchup} • ${trend.label}`;
}

function propTrendMultiplier(player) {
  const prop = primaryProp(player);
  if (!prop) return 1;
  const recent = prop.trend?.recent || {};
  const matchup = prop.trend?.vs_opponent || {};
  let factor = 1;
  if (recent.games >= 5 && Number.isFinite(Number(recent.over_rate))) {
    if (recent.over_rate >= 0.70) factor += 0.012;
    if (recent.over_rate <= 0.30) factor -= 0.012;
  }
  if (matchup.games >= 2 && Number.isFinite(Number(matchup.over_rate))) {
    if (matchup.over_rate >= 0.75) factor += 0.01;
    if (matchup.over_rate <= 0.25) factor -= 0.01;
  }
  return clamp(factor, 0.975, 1.025);
}

const matchupEdgeV3MarketMultiplier = marketMultiplier;
marketMultiplier = function(player, context) {
  const gameFactor = matchupEdgeV3MarketMultiplier(player, context);
  return clamp(gameFactor * propTrendMultiplier(player), 0.84, 1.16);
};

const matchupEdgeBasePlayerReason = playerReason;
playerReason = function(player, offense, defense, context = null) {
  const baseText = matchupEdgeBasePlayerReason(player, offense, defense, context);
  const history = playerHistorySummary(player);
  const historyText = history.games ? ` Matchup history: ${historyDisplay(player)}.` : "";
  const prop = primaryProp(player);
  const propText = prop ? ` Current player line: ${propDisplay(player)}.` : "";
  return `${baseText}${historyText}${propText}`;
};

function insertComparisonRows(html, rows) {
  if (!rows) return html;
  const marker = "</div>\n  </div>";
  const idx = html.lastIndexOf(marker);
  if (idx < 0) return html;
  return `${html.slice(0, idx)}${rows}${html.slice(idx)}`;
}

const matchupEdgeV3RenderComparisonPlayer = renderComparisonPlayer;
renderComparisonPlayer = function(analysis, leading) {
  let html = matchupEdgeV3RenderComparisonPlayer(analysis, leading);
  const player = analysis?.entry;
  if (!player || !analysis?.context || !analysis?.opponent) return html;
  const summary = playerHistorySummary(player);
  const prop = primaryProp(player);
  let rows = `<div class="factor-row"><span>Vs opponent history</span><span class="prop-detail ${historyTone(summary.trend_label)}">${historyDisplay(player)}</span></div>`;
  if (prop) {
    rows += `<div class="factor-row"><span>Player prop</span><span class="prop-detail ${historyTone(prop.trend?.label)}">${propDisplay(player)}</span></div>`;
  }
  return insertComparisonRows(html, rows);
};

const matchupEdgeV3MarketReason = marketReason;
marketReason = function(player, context) {
  const gameText = matchupEdgeV3MarketReason(player, context);
  const prop = primaryProp(player);
  if (!prop) return gameText;
  return `${gameText} Player market: ${prop.label} ${prop.consensus_line} consensus across ${prop.book_count} books; ${prop.trend?.label || "no strong prop trend"}.`;
};
