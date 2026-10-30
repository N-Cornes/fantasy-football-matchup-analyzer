from __future__ import annotations

from datetime import datetime, timezone
import json
import pandas as pd

import build_matchups as base

UNAVAILABLE_ROSTER_TOKENS = ("RES", "IR", "PUP", "NFI", "SUS", "INACTIVE")
SECONDARY = {"CB", "DB", "S", "FS", "SS"}
LINEBACKERS = {"LB", "ILB", "OLB", "MLB"}
DEF_LINE = {"DL", "DE", "DT", "NT", "EDGE"}
OFF_LINE = {"C", "G", "OG", "T", "OT", "OL", "LT", "RT", "LG", "RG"}
SKILL = {"QB", "RB", "FB", "WR", "TE"}


def text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def availability(report_status, practice_status, roster_status) -> float:
    report = text(report_status).lower()
    practice = text(practice_status).lower()
    roster = text(roster_status).upper()
    if any(token in roster for token in UNAVAILABLE_ROSTER_TOKENS):
        return 0.0
    if "out" in report:
        return 0.0
    if "doubt" in report:
        return 0.2
    if "question" in report:
        return 0.7
    if "did not" in practice or practice == "dnp":
        return 0.78
    if "limited" in practice:
        return 0.9
    return 1.0


def status_label(report_status, practice_status, roster_status) -> str:
    report = text(report_status)
    roster = text(roster_status).upper()
    practice = text(practice_status)
    if any(token in roster for token in UNAVAILABLE_ROSTER_TOKENS):
        if "PUP" in roster:
            return "PUP"
        if "NFI" in roster:
            return "NFI"
        if "SUS" in roster:
            return "SUSPENDED"
        return "IR/RESERVE"
    return (report or practice).upper()


def latest_roster_map(rosters: pd.DataFrame, positions: dict[str, dict]) -> dict[str, dict]:
    if rosters.empty or "gsis_id" not in rosters.columns:
        return {}
    df = rosters.copy()
    if "team" in df.columns:
        df["team"] = df["team"].map(base.normalize_team)
    if "week" in df.columns:
        df = df.sort_values("week")
    df = df.dropna(subset=["gsis_id"]).drop_duplicates("gsis_id", keep="last")
    out = {}
    for _, row in df.iterrows():
        pid = str(row["gsis_id"])
        info = positions.get(pid, {})
        out[pid] = {
            "team": base.normalize_team(row.get("team")),
            "position": text(row.get("position")) or info.get("position", "UNK"),
            "name": text(row.get("full_name")) or info.get("name", pid),
            "status": text(row.get("status")),
        }
    return out


def current_injuries(injuries: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if injuries.empty:
        return pd.DataFrame(), 0
    df = injuries.copy()
    if "team" in df.columns:
        df["team"] = df["team"].map(base.normalize_team)
    kind = "season_type" if "season_type" in df.columns else ("game_type" if "game_type" in df.columns else None)
    if kind:
        reg = df[df[kind].astype(str).str.upper().eq("REG")]
        if not reg.empty:
            df = reg
    week = 0
    if "week" in df.columns:
        weeks = pd.to_numeric(df["week"], errors="coerce").dropna()
        if not weeks.empty:
            week = int(weeks.max())
            df = df[pd.to_numeric(df["week"], errors="coerce").eq(week)]
    if "date_modified" in df.columns:
        df = df.sort_values("date_modified")
    if "gsis_id" in df.columns:
        df = df.dropna(subset=["gsis_id"]).drop_duplicates("gsis_id", keep="last")
    return df, week


def build_injury_context(injuries: pd.DataFrame, rosters: pd.DataFrame, positions: dict[str, dict]):
    roster_map = latest_roster_map(rosters, positions)
    current, week = current_injuries(injuries)
    player_state: dict[str, dict] = {}
    teams = {
        t: {
            "week": week,
            "offense": [],
            "defense": [],
            "offensive_line_penalty": 0.0,
            "defense_adjustments": {"pass": 0.0, "run": 0.0, "red_zone": 0.0, "wr": 0.0, "te": 0.0, "rb": 0.0},
        }
        for t in base.TEAM_NAMES
    }

    seen = set()
    for _, row in current.iterrows():
        pid = str(row.get("gsis_id"))
        seen.add(pid)
        roster = roster_map.get(pid, {})
        team = text(row.get("team")) or roster.get("team", "")
        team = base.normalize_team(team) if team else ""
        pos = text(row.get("position")) or roster.get("position") or positions.get(pid, {}).get("position", "UNK")
        name = text(row.get("full_name")) or roster.get("name") or positions.get(pid, {}).get("name", pid)
        report = text(row.get("report_status"))
        practice = text(row.get("practice_status"))
        roster_status = roster.get("status", "")
        avail = availability(report, practice, roster_status)
        player_state[pid] = {
            "week": week,
            "team": team,
            "position": pos,
            "name": name,
            "game_status": report,
            "practice_status": practice,
            "primary_injury": text(row.get("report_primary_injury")) or text(row.get("practice_primary_injury")),
            "secondary_injury": text(row.get("report_secondary_injury")) or text(row.get("practice_secondary_injury")),
            "roster_status": roster_status,
            "availability": base.round_float(avail),
            "label": status_label(report, practice, roster_status),
            "current_report": True,
        }

    for pid, roster in roster_map.items():
        if pid in seen:
            continue
        status = roster.get("status", "")
        if not any(token in status.upper() for token in UNAVAILABLE_ROSTER_TOKENS):
            continue
        player_state[pid] = {
            "week": week,
            "team": roster.get("team", ""),
            "position": roster.get("position", "UNK"),
            "name": roster.get("name", pid),
            "game_status": "",
            "practice_status": "",
            "primary_injury": "",
            "secondary_injury": "",
            "roster_status": status,
            "availability": 0.0,
            "label": status_label("", "", status),
            "current_report": False,
        }

    for pid, injury in player_state.items():
        team = injury.get("team")
        if team not in teams:
            continue
        pos = text(injury.get("position")).upper()
        avail = float(injury.get("availability", 1.0))
        severity = max(0.0, 1.0 - avail)
        if severity <= 0:
            continue
        entry = {
            "id": pid,
            "name": injury.get("name", pid),
            "position": pos,
            "label": injury.get("label", ""),
            "game_status": injury.get("game_status", ""),
            "practice_status": injury.get("practice_status", ""),
            "primary_injury": injury.get("primary_injury", ""),
            "availability": base.round_float(avail),
        }
        current_report = bool(injury.get("current_report"))
        if current_report and (pos in SKILL or pos in OFF_LINE):
            teams[team]["offense"].append(entry)
        if current_report and pos in OFF_LINE:
            teams[team]["offensive_line_penalty"] += 0.04 * severity

        if not current_report:
            continue
        adj = teams[team]["defense_adjustments"]
        if pos in SECONDARY:
            teams[team]["defense"].append(entry)
            adj["pass"] += 0.07 * severity
            adj["wr"] += 0.08 * severity
            adj["te"] += 0.025 * severity
            adj["red_zone"] += 0.02 * severity
        elif pos in LINEBACKERS:
            teams[team]["defense"].append(entry)
            adj["run"] += 0.05 * severity
            adj["rb"] += 0.05 * severity
            adj["te"] += 0.05 * severity
            adj["pass"] += 0.02 * severity
            adj["red_zone"] += 0.03 * severity
        elif pos in DEF_LINE:
            teams[team]["defense"].append(entry)
            adj["run"] += 0.05 * severity
            adj["rb"] += 0.035 * severity
            adj["pass"] += 0.025 * severity
            adj["red_zone"] += 0.02 * severity

    for ctx in teams.values():
        ctx["offensive_line_penalty"] = base.round_float(min(ctx["offensive_line_penalty"], 0.14))
        for key in ctx["defense_adjustments"]:
            ctx["defense_adjustments"][key] = base.round_float(min(ctx["defense_adjustments"][key], 0.18))
        ctx["offense"].sort(key=lambda x: (x["availability"], x["position"], x["name"]))
        ctx["defense"].sort(key=lambda x: (x["availability"], x["position"], x["name"]))
    return player_state, teams, week


def apply_defense_injuries(defenses: dict, contexts: dict):
    for team, profile in defenses.items():
        adjustments = contexts.get(team, {}).get("defense_adjustments", {})
        profile["injury_adjustments"] = adjustments
        profile["adjusted_scores"] = {
            key: base.round_float(min(1.0, float(value) + float(adjustments.get(key, 0.0))))
            for key, value in profile.get("scores", {}).items()
        }


def attach_player_injuries(usage: dict, player_state: dict):
    for players in usage.values():
        for player in players:
            player["injury"] = player_state.get(
                player["id"],
                {"availability": 1.0, "label": "", "game_status": "", "practice_status": "", "primary_injury": ""},
            )
        for pos in {"QB", "RB", "WR", "TE"}:
            group = [p for p in players if p.get("position") == pos]
            vacated = sum(float(p.get("role_score", 0)) * (1 - float(p["injury"].get("availability", 1))) for p in group)
            healthy = [p for p in group if float(p["injury"].get("availability", 1)) >= 0.65]
            healthy_role = sum(float(p.get("role_score", 0)) for p in healthy)
            for player in group:
                avail = float(player["injury"].get("availability", 1))
                boost = 0.0
                if player in healthy and healthy_role > 0 and vacated > 0:
                    boost = min(0.18, 0.65 * vacated * float(player.get("role_score", 0)) / healthy_role)
                player["injury_role_boost"] = base.round_float(boost)
                player["effective_role_score"] = base.round_float(float(player.get("role_score", 0)) * avail + boost)


def main():
    season = base.current_nfl_season()
    pbp_url = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet"
    roster_url = f"https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_{season}.parquet"
    injury_url = f"https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{season}.parquet"

    print(f"Downloading {season} play-by-play...")
    pbp = base.prepare_pbp(base.download_parquet(pbp_url))
    try:
        rosters = base.download_parquet(roster_url)
    except Exception as exc:
        print(f"Roster download failed: {exc}")
        rosters = pd.DataFrame()
    try:
        injuries = base.download_parquet(injury_url)
    except Exception as exc:
        print(f"Injury download failed: {exc}")
        injuries = pd.DataFrame()

    positions = base.build_position_map(rosters)
    defenses = base.defense_profiles(pbp, positions)
    usage = base.offensive_usage(pbp, positions)
    player_state, injury_context, injury_week = build_injury_context(injuries, rosters, positions)
    apply_defense_injuries(defenses, injury_context)
    attach_player_injuries(usage, player_state)
    through_week = int(pd.to_numeric(pbp.get("week", pd.Series([0])), errors="coerce").max())

    teams = {}
    for abbr, name in base.TEAM_NAMES.items():
        if abbr in defenses or abbr in usage:
            teams[abbr] = {
                "name": name,
                "defense": defenses.get(abbr, {"scores": {}, "adjusted_scores": {}, "stats": {}, "games": 0}),
                "players": usage.get(abbr, []),
                "injuries": injury_context.get(abbr, {}),
            }

    payload = {
        "meta": {
            "season": season,
            "through_week": through_week,
            "injury_week": injury_week,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "nflverse / nflfastR play-by-play, weekly rosters, and injury/practice reports",
            "model_version": "1.1.1",
            "injury_note": "Current-week injury reports adjust matchup strength; reserve status prevents unavailable players from being recommended without double-counting long-term absences.",
        },
        "teams": teams,
    }
    base.OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    base.OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {base.OUTPUT} with {len(teams)} teams; injury week {injury_week}")


if __name__ == "__main__":
    main()
