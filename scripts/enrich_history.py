from __future__ import annotations

import json
import math
from itertools import combinations

import numpy as np
import pandas as pd

import build_matchups as base

SCHEDULE_URL = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet"
PLAYER_STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.parquet"
HISTORY_SEASONS = 9


def clean_number(value, default=None):
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def clean_int(value, default=None):
    number = clean_number(value, default=None)
    if number is None:
        return default
    return int(number)


def finite(value):
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def robust_high_outliers(values):
    vals = np.array([float(v) for v in values if finite(v)], dtype=float)
    if len(vals) < 3:
        return set()
    median = float(np.median(vals))
    mad = float(np.median(np.abs(vals - median)))
    threshold = max(6.0, 2.5 * mad)
    return {i for i, value in enumerate(vals) if value > median + threshold and value >= max(12.0, median * 1.35)}


def player_value(row, key):
    if key == "touchdowns":
        return float(clean_number(row.get("rushing_tds"), 0) + clean_number(row.get("receiving_tds"), 0))
    aliases = {
        "passing_interceptions": ("passing_interceptions", "interceptions"),
        "rushing_attempts": ("carries", "rushing_attempts"),
        "receiving_receptions": ("receptions", "receiving_receptions"),
    }
    for col in aliases.get(key, (key,)):
        if col in row and finite(row.get(col)):
            return float(row.get(col))
    return 0.0


def compact_player_game(row):
    return {
        "season": clean_int(row.get("season"), 0),
        "week": clean_int(row.get("week"), 0),
        "game_id": str(row.get("game_id") or ""),
        "team": base.normalize_team(row.get("team")),
        "opponent": base.normalize_team(row.get("opponent_team")),
        "passing_yards": round(player_value(row, "passing_yards"), 1),
        "passing_tds": round(player_value(row, "passing_tds"), 1),
        "passing_interceptions": round(player_value(row, "passing_interceptions"), 1),
        "rushing_yards": round(player_value(row, "rushing_yards"), 1),
        "rushing_attempts": round(player_value(row, "rushing_attempts"), 1),
        "rushing_tds": round(player_value(row, "rushing_tds"), 1),
        "receiving_yards": round(player_value(row, "receiving_yards"), 1),
        "receiving_receptions": round(player_value(row, "receiving_receptions"), 1),
        "receiving_tds": round(player_value(row, "receiving_tds"), 1),
        "touchdowns": round(player_value(row, "touchdowns"), 1),
        "fantasy_points_ppr": round(player_value(row, "fantasy_points_ppr"), 2),
    }


def player_history_summary(games, recent_games):
    if not games:
        return {
            "games": 0,
            "avg_ppr": None,
            "median_ppr": None,
            "best_ppr": None,
            "baseline_recent_ppr": round(float(np.mean([g["fantasy_points_ppr"] for g in recent_games])), 2) if recent_games else None,
            "ratio_to_recent": None,
            "high_outliers": 0,
            "trend_label": "No recent matchup history",
        }

    ppr = [float(g.get("fantasy_points_ppr") or 0) for g in games]
    baseline = [float(g.get("fantasy_points_ppr") or 0) for g in recent_games]
    baseline_avg = float(np.mean(baseline)) if baseline else 0.0
    high_outlier_idx = robust_high_outliers(ppr)
    adjusted = [v for i, v in enumerate(ppr) if i not in high_outlier_idx] or ppr
    adjusted_avg = float(np.mean(adjusted))
    ratio = adjusted_avg / baseline_avg if baseline_avg >= 1 else None

    if len(games) == 1:
        label = "One-game sample — not a trend"
    elif high_outlier_idx and ratio is not None and 0.85 <= ratio <= 1.15:
        label = "One spike game — not a repeatable trend"
    elif ratio is not None and ratio >= 1.20:
        label = "Historically above baseline vs this opponent"
    elif ratio is not None and ratio <= 0.80:
        label = "Historically below baseline vs this opponent"
    else:
        label = "No strong matchup-specific trend"

    return {
        "games": len(games),
        "avg_ppr": round(float(np.mean(ppr)), 2),
        "adjusted_avg_ppr": round(adjusted_avg, 2),
        "median_ppr": round(float(np.median(ppr)), 2),
        "best_ppr": round(float(np.max(ppr)), 2),
        "baseline_recent_ppr": round(baseline_avg, 2) if baseline else None,
        "ratio_to_recent": round(ratio, 3) if ratio is not None else None,
        "high_outliers": len(high_outlier_idx),
        "trend_label": label,
    }


def load_player_history(current_season, player_ids):
    frames = []
    first_season = max(1999, current_season - HISTORY_SEASONS + 1)
    for season in range(first_season, current_season + 1):
        url = PLAYER_STATS_URL.format(season=season)
        try:
            df = base.download_parquet(url)
        except Exception as exc:
            print(f"Player history download failed for {season}: {exc}")
            continue

        id_col = "player_id" if "player_id" in df.columns else ("gsis_id" if "gsis_id" in df.columns else None)
        if not id_col:
            continue
        df[id_col] = df[id_col].astype(str)
        df = df[df[id_col].isin(player_ids)].copy()
        if df.empty:
            continue
        if id_col != "player_id":
            df["player_id"] = df[id_col]
        if "team" not in df.columns and "recent_team" in df.columns:
            df["team"] = df["recent_team"]
        if "season_type" in df.columns:
            reg = df[df["season_type"].astype(str).str.upper().eq("REG")]
            if not reg.empty:
                df = reg
        for col in ("team", "opponent_team"):
            if col in df.columns:
                df[col] = df[col].map(base.normalize_team)
        frames.append(df)

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True, sort=False)
    sort_cols = [c for c in ("season", "week") if c in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols)
    return out


def attach_player_histories(payload, stats):
    if stats.empty:
        return 0
    attached = 0
    for team_abbr, team in payload.get("teams", {}).items():
        opponent = base.normalize_team((team.get("week_context") or {}).get("opponent"))
        for player in team.get("players", []):
            pid = str(player.get("id") or "")
            if not pid:
                continue
            p = stats[stats["player_id"] == pid].copy()
            if p.empty:
                continue
            p = p.sort_values([c for c in ("season", "week") if c in p.columns])
            recent_rows = p.tail(8)
            recent_games = [compact_player_game(row) for _, row in recent_rows.iterrows()]
            matchup_rows = p[p.get("opponent_team", pd.Series(index=p.index, dtype=object)).eq(opponent)].tail(7) if opponent else p.iloc[0:0]
            matchup_games = [compact_player_game(row) for _, row in matchup_rows.iterrows()]
            player["matchup_history"] = {
                "opponent": opponent,
                "recent_games": recent_games,
                "vs_opponent_games": matchup_games,
                "summary": player_history_summary(matchup_games, recent_games),
            }
            attached += 1
    return attached


def team_game_record(row):
    return {
        "game_id": str(row.get("game_id") or ""),
        "season": clean_int(row.get("season"), 0),
        "week": clean_int(row.get("week"), 0),
        "gameday": str(row.get("gameday") or ""),
        "home_team": base.normalize_team(row.get("home_team")),
        "away_team": base.normalize_team(row.get("away_team")),
        "home_score": clean_int(row.get("home_score"), 0),
        "away_score": clean_int(row.get("away_score"), 0),
        "spread_line": round(clean_number(row.get("spread_line"), 0.0), 1) if finite(row.get("spread_line")) else None,
        "total_line": round(clean_number(row.get("total_line"), 0.0), 1) if finite(row.get("total_line")) else None,
    }


def team_perspective(game, team):
    home = game["home_team"] == team
    pf = game["home_score"] if home else game["away_score"]
    pa = game["away_score"] if home else game["home_score"]
    margin = pf - pa
    spread = game.get("spread_line")
    cover = None
    if spread is not None:
        home_margin = game["home_score"] - game["away_score"]
        delta = home_margin - spread
        if abs(delta) < 1e-9:
            home_cover = 0
        else:
            home_cover = 1 if delta > 0 else -1
        cover = home_cover if home else -home_cover
    return pf, pa, margin, cover


def team_summary(games, team):
    if not games:
        return {"games": 0, "trend_label": "No recent head-to-head history"}
    results = [team_perspective(g, team) for g in games]
    margins = [r[2] for r in results]
    points = [r[0] for r in results]
    wins = sum(1 for r in results if r[2] > 0)
    losses = sum(1 for r in results if r[2] < 0)
    ties = len(results) - wins - losses
    covers = sum(1 for r in results if r[3] == 1)
    ats_losses = sum(1 for r in results if r[3] == -1)
    pushes = sum(1 for r in results if r[3] == 0)
    ats_games = covers + ats_losses + pushes
    high_outlier_idx = robust_high_outliers(points)
    adjusted_points = [v for i, v in enumerate(points) if i not in high_outlier_idx] or points

    if len(games) < 3:
        label = "Small head-to-head sample"
    elif wins / len(games) >= 0.71:
        label = "Strong recent head-to-head results"
    elif wins / len(games) <= 0.29:
        label = "Has struggled in recent head-to-head games"
    elif ats_games >= 4 and covers / ats_games >= 0.67:
        label = "Strong recent ATS history in this matchup"
    elif ats_games >= 4 and covers / ats_games <= 0.33:
        label = "Weak recent ATS history in this matchup"
    elif high_outlier_idx and abs(float(np.mean(points)) - float(np.mean(adjusted_points))) >= 4:
        label = "Scoring average is inflated by an outlier"
    else:
        label = "No strong head-to-head trend"

    return {
        "games": len(games),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "avg_points_for": round(float(np.mean(points)), 1),
        "adjusted_avg_points_for": round(float(np.mean(adjusted_points)), 1),
        "avg_points_against": round(float(np.mean([r[1] for r in results])), 1),
        "avg_margin": round(float(np.mean(margins)), 1),
        "ats_covers": covers,
        "ats_losses": ats_losses,
        "ats_pushes": pushes,
        "ats_games": ats_games,
        "high_scoring_outliers": len(high_outlier_idx),
        "trend_label": label,
    }


def build_head_to_head(schedules, teams):
    df = schedules.copy()
    for col in ("home_team", "away_team"):
        if col in df.columns:
            df[col] = df[col].map(base.normalize_team)
    if "game_type" in df.columns:
        df = df[df["game_type"].astype(str).str.upper().isin(["REG", "WC", "DIV", "CON", "SB", "POST"])]
    df = df[df["home_score"].notna() & df["away_score"].notna()].copy()
    if "gameday" in df.columns:
        df = df.sort_values("gameday")
    else:
        df = df.sort_values([c for c in ("season", "week") if c in df.columns])

    out = {}
    for a, b in combinations(sorted(teams), 2):
        pair = df[((df["home_team"] == a) & (df["away_team"] == b)) | ((df["home_team"] == b) & (df["away_team"] == a))].tail(7)
        if pair.empty:
            continue
        games = [team_game_record(row) for _, row in pair.iterrows()]
        out[f"{a}|{b}"] = {
            "teams": [a, b],
            "games": games,
            "summary": {a: team_summary(games, a), b: team_summary(games, b)},
        }
    return out


def main():
    if not base.OUTPUT.exists():
        raise FileNotFoundError(f"Missing generated matchup data: {base.OUTPUT}")

    payload = json.loads(base.OUTPUT.read_text(encoding="utf-8"))
    current_season = int(payload.get("meta", {}).get("season") or base.current_nfl_season())
    player_ids = {
        str(player.get("id"))
        for team in payload.get("teams", {}).values()
        for player in team.get("players", [])
        if player.get("id")
    }

    stats = load_player_history(current_season, player_ids)
    attached = attach_player_histories(payload, stats)

    schedules = base.download_parquet(SCHEDULE_URL)
    head_to_head = build_head_to_head(schedules, payload.get("teams", {}).keys())
    payload["head_to_head"] = head_to_head

    meta = payload.setdefault("meta", {})
    meta["model_version"] = "1.4.0"
    meta["history_note"] = (
        "Team matchup history uses the last seven played meetings when available. Player matchup history uses up to the last seven games "
        "against the upcoming opponent and compares them with the player's recent baseline. Robust outlier checks prevent one spike game "
        "from being labeled a repeatable trend."
    )

    base.OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Attached player matchup history to {attached} players and {len(head_to_head)} team-pair histories")


if __name__ == "__main__":
    main()
