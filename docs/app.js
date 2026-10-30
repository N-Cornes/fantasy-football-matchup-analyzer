const state = { data: null };
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
    }
    if (!entries.length) throw new Error("The data pipeline has not run yet. Run the Update NFL Data workflow once in GitHub Actions.");
    const when = data.meta?.generated_at ? new Date(data.meta.generated_at).toLocaleString() : "recently";
    $("freshness").textContent = `NFL ${data.meta?.season ?? "current"} • Through Week ${data.meta?.through_week ?? "—"} • Updated ${when}`;
  })
  .catch((err) => {
    $("freshness").textContent = err.message;
    error.textContent = err.message;
  });

function validate() {
  const a = teamA.value;
  const b = teamB.value;
  analyzeBtn.disabled = !(a && b && a !== b && state.data);
  error.textContent = a && b && a === b ? "Choose two different teams." : "";
}
teamA.addEventListener("change", validate);
teamB.addEventListener("change", validate);

function pct(v) { return Math.round((Number(v) || 0) * 100); }
function share(v) { return `${Math.round((Number(v) || 0) * 100)}%`; }

function classifyWeaknesses(defense) {
  const scores = defense?.scores || {};
  const ranked = Object.entries(scores)
    .filter(([key]) => weaknessLabels[key])
    .map(([key, score]) => ({ key, score: Number(score) || 0 }))
    .sort((a, b) => b.score - a.score);

  let major = ranked.filter(x => x.score >= 0.67).slice(0, 2);
  let minor = ranked.filter(x => x.score >= 0.50 && !major.some(m => m.key === x.key)).slice(0, 2);

  // Always give the user useful information, but do not exaggerate a strong defense into a "major" weakness.
  if (!major.length && ranked[0]) minor = ranked.slice(0, 2);
  return { major, minor };
}

function weaknessDetail(item, defense) {
  const s = defense?.stats || {};
  const percentile = pct(item.score);
  switch (item.key) {
    case "pass": return `${percentile}th-percentile vulnerability. ${s.pass_yards_per_play ?? "—"} pass yards/play allowed; ${Math.round((s.explosive_pass_rate || 0) * 100)}% explosive-pass rate.`;
    case "run": return `${percentile}th-percentile vulnerability. ${s.rush_yards_per_play ?? "—"} rush yards/play allowed; ${Math.round((s.explosive_run_rate || 0) * 100)}% explosive-run rate.`;
    case "red_zone": return `${percentile}th-percentile vulnerability based on opponent touchdown rate inside the 20.`;
    case "wr": return `${percentile}th-percentile vulnerability to WR production; ${s.ppr_allowed_per_game?.WR ?? "—"} PPR points/game allowed to wide receivers.`;
    case "te": return `${percentile}th-percentile vulnerability to TE production; ${s.ppr_allowed_per_game?.TE ?? "—"} PPR points/game allowed to tight ends.`;
    case "rb": return `${percentile}th-percentile vulnerability to RB production; ${s.ppr_allowed_per_game?.RB ?? "—"} PPR points/game allowed to running backs.`;
    default: return `${percentile}th-percentile vulnerability.`;
  }
}

function playerFit(player, defense) {
  const scores = defense?.scores || {};
  let matchup = 0.5;
  if (player.position === "QB") matchup = Number(scores.pass || 0.5);
  if (player.position === "RB") matchup = Math.max(Number(scores.run || 0.5), Number(scores.rb || 0.5), Number(scores.red_zone || 0.5) * 0.85);
  if (player.position === "WR") matchup = Math.max(Number(scores.pass || 0.5), Number(scores.wr || 0.5));
  if (player.position === "TE") matchup = Math.max(Number(scores.pass || 0.5), Number(scores.te || 0.5));
  const role = Math.min(1, (Number(player.role_score) || 0) / 0.62);
  return 0.57 * role + 0.43 * matchup;
}

function playerReason(player, defense) {
  const s = defense?.scores || {};
  if (player.position === "QB") {
    return `${share(player.pass_attempt_share)} of team pass attempts. Opponent pass-defense vulnerability scores in the ${pct(s.pass)}th percentile.`;
  }
  if (player.position === "RB") {
    const matchup = Math.max(Number(s.run || 0), Number(s.rb || 0));
    return `${share(player.rush_share)} rush share, ${share(player.target_share)} target share. RB/run matchup vulnerability: ${pct(matchup)}th percentile.`;
  }
  const posScore = player.position === "TE" ? s.te : s.wr;
  return `${share(player.target_share)} season target share, ${share(player.recent_target_share)} over the last four games. ${player.position} matchup vulnerability: ${pct(posScore)}th percentile.`;
}

function likelyPlayers(offense, defense) {
  return (offense?.players || [])
    .map(p => ({ ...p, fit: playerFit(p, defense) }))
    .filter(p => p.fit >= 0.39)
    .sort((a, b) => b.fit - a.fit)
    .slice(0, 4);
}

function confidence(fit) {
  if (fit >= 0.76) return "HIGH";
  if (fit >= 0.59) return "MEDIUM";
  return "WATCH";
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

function directionCard(offenseAbbr, defenseAbbr) {
  const offense = state.data.teams[offenseAbbr];
  const defenseTeam = state.data.teams[defenseAbbr];
  const defense = defenseTeam.defense;
  const weaknesses = classifyWeaknesses(defense);
  const players = likelyPlayers(offense, defense);
  const weaknessHtml = [
    ...weaknesses.major.map(x => renderWeakness(x, "major", defense)),
    ...weaknesses.minor.map(x => renderWeakness(x, "minor", defense)),
  ].join("") || `<p class="empty">No clear defensive weakness is showing above league average right now.</p>`;

  const playersHtml = players.map(p => `<div class="player">
    <div class="player-top">
      <div><span class="player-name">${p.name}</span><span class="player-pos">${p.position}</span></div>
      <span class="confidence">${confidence(p.fit)}</span>
    </div>
    <p>${playerReason(p, defense)}</p>
  </div>`).join("") || `<p class="empty">Not enough usage data to make a player recommendation.</p>`;

  return `<article class="direction">
    <div class="direction-head">
      <h2><b>${offense.name}</b> offense vs. ${defenseTeam.name} defense</h2>
      <span class="direction-tag">${defense.games || 0} games analyzed</span>
    </div>
    <div class="grid">
      <div class="card">
        <h3>Defensive weaknesses</h3>
        <div class="weakness-list">${weaknessHtml}</div>
      </div>
      <div class="card">
        <h3>Players most likely to be featured</h3>
        <div class="player-list">${playersHtml}</div>
      </div>
    </div>
  </article>`;
}

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
