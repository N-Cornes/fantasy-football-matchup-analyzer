from __future__ import annotations

import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "data" / "matchups.json"

TEAM_NAMES = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "LA": "Los Angeles Rams", "LAC": "Los Angeles Chargers",
    "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings",
    "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks", "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}

TEAM_ALIASES = {"JAC": "JAX", "LAR": "LA", "OAK": "LV", "SD": "LAC", "STL": "LA"}


def current_nfl_season(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    return now.year if now.month >= 3 else now.year - 1


def download_parquet(url: str) -> pd.DataFrame:
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    return pd.read_parquet(io.BytesIO(response.content))


def normalize_team(value):
    if pd.isna(value):
        return value
    value = str(value)
    return TEAM_ALIASES.get(value, value)


def num(value, default=0.0):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_mean(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    value = series.mean()
    return 0.0 if pd.isna(value) else float(value)


def pct_rank(series: pd.Series, higher_is_worse: bool = True) -> pd.Series:
    s = series.astype(float)
    rank = s.rank(method="average", pct=True)
    return rank if higher_is_worse else (1.0 - rank + (1.0 / max(len(s), 1)))


def round_float(value, digits=3):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return 0.0
    return round(float(value), digits)


def build_position_map(rosters: pd.DataFrame) -> dict[str, dict]:
    if rosters.empty:
        return {}
    rosters = rosters.copy()
    if "team" in rosters:
        rosters["team"] = rosters["team"].map(normalize_team)
    if "week" in rosters:
        rosters = rosters.sort_values("week")
    id_col = "gsis_id" if "gsis_id" in rosters.columns else None
    if not id_col:
        return {}
    latest = rosters.dropna(subset=[id_col]).drop_duplicates(id_col, keep="last")
    mapping = {}
    for _, row in latest.iterrows():
        pid = str(row[id_col])
        name = row.get("full_name") or row.get("football_name") or row.get("last_name") or pid
        pos = str(row.get("position") or "UNK")
        team = normalize_team(row.get("team"))
        mapping[pid] = {"name": str(name), "position": pos, "team": team}
    return mapping


def prepare_pbp(pbp: pd.DataFrame) -> pd.DataFrame:
    pbp = pbp.copy()
    for col in ["posteam", "defteam"]:
        if col in pbp:
            pbp[col] = pbp[col].map(normalize_team)
    if "season_type" in pbp.columns:
        reg = pbp[pbp["season_type"].astype(str).str.upper().eq("REG")]
        if not reg.empty:
            pbp = reg
    if "play_type" in pbp.columns:
        pbp = pbp[pbp["play_type"].isin(["pass", "run"])]
    return pbp[pbp["posteam"].notna() & pbp["defteam"].notna()].copy()


def defense_profiles(pbp: pd.DataFrame, position_map: dict[str, dict]) -> dict[str, dict]:
    records = []
    teams = sorted(set(pbp["defteam"].dropna()) & set(TEAM_NAMES))

    for team in teams:
        d = pbp[pbp["defteam"] == team]
        p = d[d["play_type"] == "pass"]
        r = d[d["play_type"] == "run"]
        games = max(int(d["game_id"].nunique()) if "game_id" in d else int(d["week"].nunique()), 1)

        pass_epa = safe_mean(p["epa"]) if "epa" in p else 0
        rush_epa = safe_mean(r["epa"]) if "epa" in r else 0
        pass_ypp = safe_mean(p["yards_gained"].clip(-20, 80)) if "yards_gained" in p else 0
        rush_ypp = safe_mean(r["yards_gained"].clip(-20, 80)) if "yards_gained" in r else 0
        pass_explosive = safe_mean((p["yards_gained"] >= 20).astype(float)) if "yards_gained" in p else 0
        rush_explosive = safe_mean((r["yards_gained"] >= 10).astype(float)) if "yards_gained" in r else 0
        pass_td_rate = safe_mean(p.get("pass_touchdown", pd.Series(index=p.index, dtype=float)).fillna(0))
        rush_td_rate = safe_mean(r.get("rush_touchdown", pd.Series(index=r.index, dtype=float)).fillna(0))
        sack_rate = safe_mean(p.get("sack", pd.Series(index=p.index, dtype=float)).fillna(0))

        red = d[d.get("yardline_100", pd.Series(index=d.index, dtype=float)).le(20)] if "yardline_100" in d else d.iloc[0:0]
        red_td_rate = safe_mean(red.get("touchdown", pd.Series(index=red.index, dtype=float)).fillna(0)) if not red.empty else 0

        records.append({
            "team": team, "games": games,
            "pass_epa": pass_epa, "pass_ypp": pass_ypp, "pass_explosive": pass_explosive,
            "pass_td_rate": pass_td_rate, "sack_rate": sack_rate,
            "rush_epa": rush_epa, "rush_ypp": rush_ypp, "rush_explosive": rush_explosive,
            "rush_td_rate": rush_td_rate, "red_td_rate": red_td_rate,
        })

    df = pd.DataFrame(records).set_index("team")
    if df.empty:
        return {}

    pass_score = (
        0.35 * pct_rank(df["pass_epa"], True)
        + 0.25 * pct_rank(df["pass_ypp"], True)
        + 0.20 * pct_rank(df["pass_explosive"], True)
        + 0.10 * pct_rank(df["pass_td_rate"], True)
        + 0.10 * pct_rank(df["sack_rate"], False)
    )
    rush_score = (
        0.35 * pct_rank(df["rush_epa"], True)
        + 0.30 * pct_rank(df["rush_ypp"], True)
        + 0.20 * pct_rank(df["rush_explosive"], True)
        + 0.15 * pct_rank(df["rush_td_rate"], True)
    )
    red_score = pct_rank(df["red_td_rate"], True)

    # Fantasy points allowed by position, per game. This makes the recommendations useful for fantasy football.
    position_points = []
    for _, row in pbp.iterrows():
        defense = row.get("defteam")
        game_id = row.get("game_id")
        if not defense or not game_id:
            continue

        if row.get("play_type") == "pass" and pd.notna(row.get("receiver_player_id")):
            pid = str(row.get("receiver_player_id"))
            info = position_map.get(pid, {})
            pos = info.get("position", "UNK")
            if pos in {"WR", "TE", "RB", "FB"}:
                complete = num(row.get("complete_pass"))
                yards = num(row.get("yards_gained")) if complete else 0.0
                td = num(row.get("pass_touchdown"))
                points = complete + yards / 10.0 + td * 6.0
                position_points.append((defense, game_id, "RB" if pos == "FB" else pos, points))

        if row.get("play_type") == "run" and pd.notna(row.get("rusher_player_id")):
            pid = str(row.get("rusher_player_id"))
            info = position_map.get(pid, {})
            pos = info.get("position", "UNK")
            if pos in {"RB", "FB", "QB"}:
                yards = num(row.get("yards_gained"))
                td = num(row.get("rush_touchdown"))
                points = yards / 10.0 + td * 6.0
                position_points.append((defense, game_id, "RB" if pos == "FB" else pos, points))

    pos_scores = {team: {"WR": 0.5, "TE": 0.5, "RB": 0.5} for team in df.index}
    pos_values = {team: {"WR": 0.0, "TE": 0.0, "RB": 0.0} for team in df.index}
    if position_points:
        pos_df = pd.DataFrame(position_points, columns=["team", "game_id", "position", "points"])
        per_game = pos_df.groupby(["team", "position", "game_id"], as_index=False)["points"].sum()
        avg = per_game.groupby(["team", "position"])["points"].mean().unstack(fill_value=0)
        for pos in ["WR", "TE", "RB"]:
            if pos not in avg.columns:
                continue
            ranked = pct_rank(avg[pos].reindex(df.index, fill_value=0), True)
            for team in df.index:
                pos_scores[team][pos] = float(ranked.loc[team])
                pos_values[team][pos] = float(avg[pos].reindex(df.index, fill_value=0).loc[team])

    profiles = {}
    for team in df.index:
        profiles[team] = {
            "games": int(df.loc[team, "games"]),
            "scores": {
                "pass": round_float(pass_score.loc[team]),
                "run": round_float(rush_score.loc[team]),
                "red_zone": round_float(red_score.loc[team]),
                "wr": round_float(pos_scores[team]["WR"]),
                "te": round_float(pos_scores[team]["TE"]),
                "rb": round_float(pos_scores[team]["RB"]),
            },
            "stats": {
                "pass_epa_allowed": round_float(df.loc[team, "pass_epa"]),
                "pass_yards_per_play": round_float(df.loc[team, "pass_ypp"], 2),
                "explosive_pass_rate": round_float(df.loc[team, "pass_explosive"]),
                "rush_epa_allowed": round_float(df.loc[team, "rush_epa"]),
                "rush_yards_per_play": round_float(df.loc[team, "rush_ypp"], 2),
                "explosive_run_rate": round_float(df.loc[team, "rush_explosive"]),
                "red_zone_td_rate": round_float(df.loc[team, "red_td_rate"]),
                "ppr_allowed_per_game": {k: round_float(v, 2) for k, v in pos_values[team].items()},
            },
        }
    return profiles


def offensive_usage(pbp: pd.DataFrame, position_map: dict[str, dict]) -> dict[str, list[dict]]:
    max_week = int(pd.to_numeric(pbp.get("week", pd.Series([1])), errors="coerce").max())
    recent_start = max(1, max_week - 3)
    teams = sorted(set(pbp["posteam"].dropna()) & set(TEAM_NAMES))
    result = {}

    for team in teams:
        t = pbp[pbp["posteam"] == team].copy()
        recent = t[t.get("week", 0) >= recent_start].copy()
        players: dict[str, dict] = {}

        def ensure(pid, fallback_name=None):
            pid = str(pid)
            if pid not in players:
                info = position_map.get(pid, {})
                players[pid] = {
                    "id": pid,
                    "name": info.get("name") or fallback_name or pid,
                    "position": info.get("position") or "UNK",
                    "targets": 0, "receptions": 0, "rec_yards": 0.0, "rec_tds": 0,
                    "carries": 0, "rush_yards": 0.0, "rush_tds": 0,
                    "pass_attempts": 0, "pass_yards": 0.0, "pass_tds": 0, "ints": 0,
                    "rz_targets": 0, "rz_carries": 0,
                    "recent_targets": 0, "recent_carries": 0, "recent_pass_attempts": 0,
                }
            return players[pid]

        for _, row in t.iterrows():
            in_recent = bool(num(row.get("week"), 0) >= recent_start)
            rz = bool(pd.notna(row.get("yardline_100")) and num(row.get("yardline_100"), 999) <= 20)

            passer_id = row.get("passer_player_id")
            if row.get("play_type") == "pass" and pd.notna(passer_id):
                p = ensure(passer_id, row.get("passer_player_name"))
                p["pass_attempts"] += 1
                if in_recent: p["recent_pass_attempts"] += 1
                if num(row.get("complete_pass")):
                    p["pass_yards"] += num(row.get("yards_gained"))
                p["pass_tds"] += int(num(row.get("pass_touchdown")))
                p["ints"] += int(num(row.get("interception")))
                if p["position"] == "UNK": p["position"] = "QB"

            receiver_id = row.get("receiver_player_id")
            if row.get("play_type") == "pass" and pd.notna(receiver_id):
                p = ensure(receiver_id, row.get("receiver_player_name"))
                p["targets"] += 1
                if in_recent: p["recent_targets"] += 1
                if rz: p["rz_targets"] += 1
                if num(row.get("complete_pass")):
                    p["receptions"] += 1
                    p["rec_yards"] += num(row.get("yards_gained"))
                    p["rec_tds"] += int(num(row.get("pass_touchdown")))

            rusher_id = row.get("rusher_player_id")
            if row.get("play_type") == "run" and pd.notna(rusher_id):
                p = ensure(rusher_id, row.get("rusher_player_name"))
                p["carries"] += 1
                if in_recent: p["recent_carries"] += 1
                if rz: p["rz_carries"] += 1
                p["rush_yards"] += num(row.get("yards_gained"))
                p["rush_tds"] += int(num(row.get("rush_touchdown")))

        total_targets = max(sum(p["targets"] for p in players.values()), 1)
        total_carries = max(sum(p["carries"] for p in players.values()), 1)
        total_rz_targets = max(sum(p["rz_targets"] for p in players.values()), 1)
        total_rz_carries = max(sum(p["rz_carries"] for p in players.values()), 1)
        recent_targets = max(sum(p["recent_targets"] for p in players.values()), 1)
        recent_carries = max(sum(p["recent_carries"] for p in players.values()), 1)
        total_pass_attempts = max(sum(p["pass_attempts"] for p in players.values()), 1)
        recent_pass_attempts = max(sum(p["recent_pass_attempts"] for p in players.values()), 1)

        output = []
        for p in players.values():
            pos = p["position"]
            if pos == "FB": pos = "RB"
            if pos not in {"QB", "RB", "WR", "TE"}:
                if p["pass_attempts"] > 8:
                    pos = "QB"
                elif p["carries"] >= max(4, p["targets"]):
                    pos = "RB"
                elif p["targets"] > 0:
                    pos = "WR"
                else:
                    continue

            target_share = p["targets"] / total_targets
            rush_share = p["carries"] / total_carries
            recent_target_share = p["recent_targets"] / recent_targets
            recent_rush_share = p["recent_carries"] / recent_carries
            rz_target_share = p["rz_targets"] / total_rz_targets
            rz_rush_share = p["rz_carries"] / total_rz_carries
            pass_share = p["pass_attempts"] / total_pass_attempts
            recent_pass_share = p["recent_pass_attempts"] / recent_pass_attempts

            if pos == "QB":
                role = 0.65 * pass_share + 0.35 * recent_pass_share
            elif pos == "RB":
                role = 0.40 * rush_share + 0.25 * recent_rush_share + 0.18 * target_share + 0.17 * rz_rush_share
            else:
                role = 0.45 * target_share + 0.30 * recent_target_share + 0.25 * rz_target_share

            # Filter out very small roles so a random one-play player never appears as a recommendation.
            if role < 0.035 and p["targets"] + p["carries"] + p["pass_attempts"] < 8:
                continue

            output.append({
                "id": p["id"], "name": p["name"], "position": pos,
                "role_score": round_float(role),
                "target_share": round_float(target_share), "rush_share": round_float(rush_share),
                "recent_target_share": round_float(recent_target_share), "recent_rush_share": round_float(recent_rush_share),
                "red_zone_target_share": round_float(rz_target_share), "red_zone_rush_share": round_float(rz_rush_share),
                "pass_attempt_share": round_float(pass_share),
                "season": {
                    "targets": p["targets"], "receptions": p["receptions"], "receiving_yards": round_float(p["rec_yards"], 1),
                    "receiving_tds": p["rec_tds"], "carries": p["carries"], "rushing_yards": round_float(p["rush_yards"], 1),
                    "rushing_tds": p["rush_tds"], "pass_attempts": p["pass_attempts"], "passing_yards": round_float(p["pass_yards"], 1),
                    "passing_tds": p["pass_tds"], "interceptions": p["ints"],
                },
            })

        output.sort(key=lambda x: x["role_score"], reverse=True)
        result[team] = output[:12]
    return result


def main():
    season = current_nfl_season()
    pbp_url = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet"
    roster_url = f"https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_{season}.parquet"

    print(f"Downloading {season} nflverse play-by-play...")
    pbp = prepare_pbp(download_parquet(pbp_url))
    print(f"Loaded {len(pbp):,} offensive plays")

    try:
        rosters = download_parquet(roster_url)
    except Exception as exc:
        print(f"Roster download failed ({exc}); continuing with play-by-play name inference.")
        rosters = pd.DataFrame()

    position_map = build_position_map(rosters)
    defenses = defense_profiles(pbp, position_map)
    usage = offensive_usage(pbp, position_map)
    max_week = int(pd.to_numeric(pbp.get("week", pd.Series([0])), errors="coerce").max())

    teams = {}
    for abbr, name in TEAM_NAMES.items():
        if abbr in defenses or abbr in usage:
            teams[abbr] = {
                "name": name,
                "defense": defenses.get(abbr, {"scores": {}, "stats": {}, "games": 0}),
                "players": usage.get(abbr, []),
            }

    payload = {
        "meta": {
            "season": season,
            "through_week": max_week,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "nflverse / nflfastR play-by-play and weekly roster data",
            "model_version": "1.0.0",
        },
        "teams": teams,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT} with {len(teams)} teams")


if __name__ == "__main__":
    main()
