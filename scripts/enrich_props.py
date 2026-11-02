from __future__ import annotations

import json
import os
import re
import statistics
import unicodedata
from datetime import datetime, timedelta, timezone

import requests

import build_matchups as base

API_URL = "https://api.sportsgameodds.com/v2/events"
SUPPORTED_STATS = {
    "passing_yards": "Passing yards",
    "passing_touchdowns": "Passing TDs",
    "passing_completions": "Pass completions",
    "passing_attempts": "Pass attempts",
    "passing_interceptions": "Interceptions thrown",
    "rushing_yards": "Rushing yards",
    "rushing_attempts": "Rush attempts",
    "receiving_yards": "Receiving yards",
    "receiving_receptions": "Receptions",
    "touchdowns": "Anytime touchdowns",
}

HISTORY_KEYS = {
    "passing_yards": "passing_yards",
    "passing_touchdowns": "passing_tds",
    "passing_completions": "completions",
    "passing_attempts": "attempts",
    "passing_interceptions": "passing_interceptions",
    "rushing_yards": "rushing_yards",
    "rushing_attempts": "rushing_attempts",
    "receiving_yards": "receiving_yards",
    "receiving_receptions": "receiving_receptions",
    "touchdowns": "touchdowns",
}


def number(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("’", "'")
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def nested_player(event, player_id):
    players = event.get("players") or {}
    if isinstance(players, dict):
        direct = players.get(player_id)
        if isinstance(direct, dict):
            return direct
        for value in players.values():
            if isinstance(value, dict):
                if value.get("playerID") == player_id:
                    return value
                nested = value.get(player_id)
                if isinstance(nested, dict):
                    return nested
    return {}


def player_name_from_event(event, player_id, odd):
    player = nested_player(event, player_id)
    names = player.get("names") if isinstance(player, dict) else None
    if isinstance(names, dict):
        for key in ("display", "name", "full"):
            if names.get(key):
                return str(names[key])
    if isinstance(player, dict):
        for key in ("name", "displayName", "fullName"):
            if player.get(key):
                return str(player[key])

    market_name = str(odd.get("marketName") or "")
    stat_label = SUPPORTED_STATS.get(odd.get("statID"), "")
    if market_name and stat_label:
        cut_tokens = [" Passing ", " Rushing ", " Receiving ", " Receptions", " Any Touchdown", " Touchdowns"]
        for token in cut_tokens:
            idx = market_name.lower().find(token.lower())
            if idx > 0:
                return market_name[:idx].strip()
    return ""


def event_player_team(event, player_id):
    player = nested_player(event, player_id)
    if isinstance(player, dict):
        return str(player.get("teamID") or player.get("team") or "")
    return ""


def line_history(games, stat_key, line):
    values = []
    for game in games or []:
        value = number(game.get(stat_key))
        if value is not None:
            values.append(value)
    if not values:
        return {"games": 0, "overs": 0, "unders": 0, "pushes": 0, "over_rate": None, "summary": "No sample"}
    overs = sum(v > line for v in values)
    unders = sum(v < line for v in values)
    pushes = len(values) - overs - unders
    graded = overs + unders
    rate = overs / graded if graded else None
    return {
        "games": len(values),
        "overs": overs,
        "unders": unders,
        "pushes": pushes,
        "over_rate": round(rate, 3) if rate is not None else None,
        "average": round(sum(values) / len(values), 2),
        "summary": f"{overs}-{unders}-{pushes} vs today's line",
    }


def trend_label(recent, matchup):
    r_games = recent.get("games", 0)
    r_rate = recent.get("over_rate")
    m_games = matchup.get("games", 0)
    m_rate = matchup.get("over_rate")
    if m_games >= 2 and m_rate is not None and m_rate >= 0.75:
        return "Strong history clearing this line vs opponent"
    if m_games >= 2 and m_rate is not None and m_rate <= 0.25:
        return "Historically below this line vs opponent"
    if r_games >= 5 and r_rate is not None and r_rate >= 0.70:
        return "Strong recent over trend vs current line"
    if r_games >= 5 and r_rate is not None and r_rate <= 0.30:
        return "Strong recent under trend vs current line"
    return "No strong line-clearing trend"


def compile_prop(odd, history):
    books = []
    for book, data in (odd.get("byBookmaker") or {}).items():
        if not isinstance(data, dict) or data.get("available") is False:
            continue
        line = number(data.get("overUnder"))
        odds = data.get("odds")
        if line is None:
            continue
        books.append({
            "bookmaker": book,
            "line": line,
            "odds": odds,
            "updated_at": data.get("lastUpdatedAt"),
            "deeplink": data.get("deeplink"),
        })
    if not books:
        return None

    lines = [b["line"] for b in books]
    consensus = float(statistics.median(lines))
    stat_id = odd.get("statID")
    history_key = HISTORY_KEYS.get(stat_id)
    recent_games = (history or {}).get("recent_games", [])
    matchup_games = (history or {}).get("vs_opponent_games", [])
    recent = line_history(recent_games, history_key, consensus) if history_key else {"games": 0}
    matchup = line_history(matchup_games, history_key, consensus) if history_key else {"games": 0}

    return {
        "market": stat_id,
        "label": SUPPORTED_STATS.get(stat_id, stat_id),
        "consensus_line": round(consensus, 2),
        "fair_line": number(odd.get("fairOverUnder")),
        "book_consensus_line": number(odd.get("bookOverUnder")),
        "fair_over_odds": odd.get("fairOdds"),
        "book_over_odds": odd.get("bookOdds"),
        "book_count": len(books),
        "line_min": round(min(lines), 2),
        "line_max": round(max(lines), 2),
        "books": books,
        "trend": {
            "recent": recent,
            "vs_opponent": matchup,
            "label": trend_label(recent, matchup),
        },
    }


def fetch_events(api_key):
    now = datetime.now(timezone.utc)
    params = {
        "leagueID": "NFL",
        "oddsAvailable": "true",
        "started": "false",
        "startsAfter": (now - timedelta(hours=3)).isoformat().replace("+00:00", "Z"),
        "startsBefore": (now + timedelta(days=9)).isoformat().replace("+00:00", "Z"),
        "limit": 100,
        "includeAltLines": "false",
    }
    response = requests.get(API_URL, headers={"x-api-key": api_key}, params=params, timeout=90)
    response.raise_for_status()
    body = response.json()
    if not body.get("success", True):
        raise RuntimeError(body.get("error") or "SportsGameOdds request failed")
    data = body.get("data") or body.get("events") or []
    return data if isinstance(data, list) else []


def build_current_player_index(payload):
    index = {}
    for team_abbr, team in payload.get("teams", {}).items():
        for player in team.get("players", []):
            key = clean_name(player.get("name"))
            if not key:
                continue
            index.setdefault(key, []).append((team_abbr, player))
    return index


def attach_props(payload, events):
    index = build_current_player_index(payload)
    attached = 0
    event_count = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        event_count += 1
        for odd in (event.get("odds") or {}).values():
            if not isinstance(odd, dict):
                continue
            stat_id = odd.get("statID")
            if stat_id not in SUPPORTED_STATS:
                continue
            if odd.get("betTypeID") != "ou" or odd.get("sideID") != "over":
                continue
            if odd.get("periodID") not in ("game", "reg", None):
                continue
            player_id = odd.get("playerID") or odd.get("statEntityID")
            if not player_id or str(player_id) in {"all", "home", "away"}:
                continue
            player_name = player_name_from_event(event, str(player_id), odd)
            key = clean_name(player_name)
            candidates = index.get(key, [])
            if not candidates:
                continue
            if len(candidates) > 1:
                # Current NFL skill-player display names are almost always unique. If not,
                # attach only when the player's current matchup supplies enough context later.
                candidates = candidates[:1]
            for team_abbr, player in candidates:
                prop = compile_prop(odd, player.get("matchup_history") or {})
                if not prop:
                    continue
                props = player.setdefault("props", {})
                existing = props.get(stat_id)
                if existing and int(existing.get("book_count", 0)) >= int(prop.get("book_count", 0)):
                    continue
                prop["source"] = "SportsGameOdds"
                prop["event_id"] = event.get("eventID")
                prop["player_source_id"] = str(player_id)
                props[stat_id] = prop
                attached += 1

    return attached, event_count


def main():
    if not base.OUTPUT.exists():
        raise FileNotFoundError(f"Missing generated matchup data: {base.OUTPUT}")

    payload = json.loads(base.OUTPUT.read_text(encoding="utf-8"))
    meta = payload.setdefault("meta", {})
    api_key = os.getenv("SPORTSGAMEODDS_API_KEY", "").strip()

    meta["player_prop_source"] = "SportsGameOdds free Amateur tier"
    meta["player_prop_note"] = (
        "Current NFL player prop lines are aggregated from available sportsbooks. Matchup Edge uses the median posted line across books "
        "and compares today's line with nflverse player results. A historical hit rate against today's line is not the same as a historical "
        "record against each game's original closing prop."
    )

    if not api_key:
        meta["player_props_configured"] = False
        meta["player_props_updated_at"] = None
        base.OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print("SPORTSGAMEODDS_API_KEY is not configured; player prop feed skipped")
        return

    events = fetch_events(api_key)
    attached, event_count = attach_props(payload, events)
    meta["player_props_configured"] = True
    meta["player_props_updated_at"] = datetime.now(timezone.utc).isoformat()
    meta["player_props_events"] = event_count
    meta["player_props_markets_attached"] = attached
    meta["model_version"] = "1.5.0"

    base.OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Attached {attached} player prop markets from {event_count} upcoming NFL events")


if __name__ == "__main__":
    main()
