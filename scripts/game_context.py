from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests

import build_matchups as base

SCHEDULE_URL = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet"

# Stadium-area coordinates. Weather is skipped for domes/closed roofs.
TEAM_COORDS = {
    "ARI": (33.5276, -112.2626), "ATL": (33.7554, -84.4008),
    "BAL": (39.2780, -76.6227), "BUF": (42.7738, -78.7870),
    "CAR": (35.2258, -80.8528), "CHI": (41.8623, -87.6167),
    "CIN": (39.0954, -84.5160), "CLE": (41.5061, -81.6995),
    "DAL": (32.7473, -97.0945), "DEN": (39.7439, -105.0201),
    "DET": (42.3400, -83.0456), "GB": (44.5013, -88.0622),
    "HOU": (29.6847, -95.4107), "IND": (39.7601, -86.1639),
    "JAX": (30.3239, -81.6373), "KC": (39.0489, -94.4839),
    "LA": (33.9535, -118.3392), "LAC": (33.9535, -118.3392),
    "LV": (36.0908, -115.1830), "MIA": (25.9580, -80.2389),
    "MIN": (44.9736, -93.2575), "NE": (42.0909, -71.2643),
    "NO": (29.9511, -90.0812), "NYG": (40.8135, -74.0745),
    "NYJ": (40.8135, -74.0745), "PHI": (39.9008, -75.1675),
    "PIT": (40.4468, -80.0158), "SEA": (47.5952, -122.3316),
    "SF": (37.4030, -121.9697), "TB": (27.9759, -82.5033),
    "TEN": (36.1665, -86.7713), "WAS": (38.9076, -76.8645),
}

PROTECTED_ROOFS = {"dome", "closed"}


def clean_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def clean_number(value, default=None):
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def load_schedules() -> pd.DataFrame:
    schedules = base.download_parquet(SCHEDULE_URL).copy()
    for col in ("home_team", "away_team"):
        if col in schedules.columns:
            schedules[col] = schedules[col].map(base.normalize_team)
    schedules["game_date"] = pd.to_datetime(schedules.get("gameday"), errors="coerce")
    return schedules


def team_spread(row: pd.Series, team: str):
    spread = clean_number(row.get("spread_line"))
    if spread is None:
        return None
    home = base.normalize_team(row.get("home_team"))
    # nflverse spread_line is positive when the home team is favored.
    # Convert to conventional team betting line: favorite is negative.
    return -spread if team == home else spread


def team_margin(row: pd.Series, team: str):
    home_score = clean_number(row.get("home_score"))
    away_score = clean_number(row.get("away_score"))
    if home_score is None or away_score is None:
        return None
    home = base.normalize_team(row.get("home_team"))
    return (home_score - away_score) if team == home else (away_score - home_score)


def ats_record(rows: pd.DataFrame, team: str) -> dict:
    covers = losses = pushes = outright_wins = 0
    decisions = 0
    for _, row in rows.iterrows():
        line = team_spread(row, team)
        margin = team_margin(row, team)
        if line is None or margin is None:
            continue
        ats = margin + line
        if ats > 0.01:
            covers += 1
            decisions += 1
        elif ats < -0.01:
            losses += 1
            decisions += 1
        else:
            pushes += 1
        if margin > 0:
            outright_wins += 1
    total = covers + losses + pushes
    return {
        "covers": covers,
        "losses": losses,
        "pushes": pushes,
        "games": total,
        "cover_rate": base.round_float(covers / decisions if decisions else 0.0),
        "outright_win_rate": base.round_float(outright_wins / total if total else 0.0),
        "summary": f"{covers}-{losses}-{pushes} ATS",
    }


def over_record(rows: pd.DataFrame) -> dict:
    overs = unders = pushes = 0
    for _, row in rows.iterrows():
        actual = clean_number(row.get("total"))
        line = clean_number(row.get("total_line"))
        if actual is None or line is None:
            continue
        diff = actual - line
        if diff > 0.01:
            overs += 1
        elif diff < -0.01:
            unders += 1
        else:
            pushes += 1
    decisions = overs + unders
    total = decisions + pushes
    return {
        "overs": overs,
        "unders": unders,
        "pushes": pushes,
        "games": total,
        "over_rate": base.round_float(overs / decisions if decisions else 0.0),
        "summary": f"{overs}-{unders}-{pushes} O/U",
    }


def market_history(schedules: pd.DataFrame, team: str, before_date, current_line) -> dict:
    cutoff = pd.Timestamp(before_date)
    seasons = pd.to_numeric(schedules.get("season"), errors="coerce")
    min_season = max(int(cutoff.year) - 3, 2020)
    played = schedules[
        seasons.ge(min_season)
        & schedules["game_date"].lt(cutoff)
        & schedules.get("home_score", pd.Series(index=schedules.index, dtype=float)).notna()
        & schedules.get("away_score", pd.Series(index=schedules.index, dtype=float)).notna()
        & schedules.get("spread_line", pd.Series(index=schedules.index, dtype=float)).notna()
        & (
            schedules.get("home_team", pd.Series(index=schedules.index, dtype=object)).eq(team)
            | schedules.get("away_team", pd.Series(index=schedules.index, dtype=object)).eq(team)
        )
    ].sort_values("game_date")

    recent8 = played.tail(8)
    recent16 = played.tail(16)

    role_rows = []
    similar_rows = []
    current_role = "pick'em"
    if current_line is not None:
        current_role = "favorite" if current_line < 0 else ("underdog" if current_line > 0 else "pick'em")
        for idx, row in played.tail(32).iterrows():
            line = team_spread(row, team)
            if line is None:
                continue
            role = "favorite" if line < 0 else ("underdog" if line > 0 else "pick'em")
            if role == current_role:
                role_rows.append(idx)
            if abs(line - current_line) <= 2.0:
                similar_rows.append(idx)

    role_df = played.loc[role_rows] if role_rows else played.iloc[0:0]
    similar_df = played.loc[similar_rows] if similar_rows else played.iloc[0:0]

    recent = ats_record(recent8, team)
    same_role = ats_record(role_df.tail(16), team)
    similar = ats_record(similar_df.tail(12), team)
    over = over_record(recent8)

    label = "No strong ATS trend"
    if recent["games"] >= 6 and recent["cover_rate"] >= 0.625:
        label = "Recent market-beating trend"
    elif recent["games"] >= 6 and recent["cover_rate"] <= 0.375:
        label = "Recent market-underperformance"
    elif same_role["games"] >= 6 and same_role["cover_rate"] >= 0.62:
        label = f"Strong ATS trend as {current_role}"
    elif same_role["games"] >= 6 and same_role["cover_rate"] <= 0.38:
        label = f"Weak ATS trend as {current_role}"

    return {
        "role": current_role,
        "recent_8": recent,
        "recent_16": ats_record(recent16, team),
        "same_role": same_role,
        "similar_line": similar,
        "recent_totals": over,
        "trend_label": label,
    }


def kickoff_utc(row: pd.Series):
    date_value = pd.to_datetime(row.get("gameday"), errors="coerce")
    if pd.isna(date_value):
        return None
    game_time = clean_text(row.get("gametime")) or "13:00"
    try:
        hh, mm = [int(x) for x in game_time.split(":")[:2]]
    except Exception:
        hh, mm = 13, 0
    # nflverse gametime is listed in US Eastern time.
    eastern = ZoneInfo("America/New_York")
    local = datetime.combine(date_value.date(), time(hh, mm), tzinfo=eastern)
    return local.astimezone(timezone.utc)


def weather_multipliers(temp_f, wind_mph, gust_mph, precip_probability, precip_in) -> dict:
    passing = 1.0
    rushing = 1.0
    wind = max(wind_mph or 0.0, (gust_mph or 0.0) * 0.70)
    if wind >= 20:
        passing -= 0.10
        rushing += 0.02
    elif wind >= 15:
        passing -= 0.05
        rushing += 0.01

    wet = (precip_probability or 0.0) >= 60 or (precip_in or 0.0) >= 0.05
    if wet:
        passing -= 0.04
        rushing += 0.01

    if temp_f is not None and temp_f <= 20:
        passing -= 0.04
    elif temp_f is not None and temp_f <= 32:
        passing -= 0.02
    elif temp_f is not None and temp_f >= 92:
        passing -= 0.01
        rushing -= 0.01

    passing = max(0.84, min(1.04, passing))
    rushing = max(0.94, min(1.05, rushing))
    return {
        "QB": base.round_float(passing),
        "WR": base.round_float(passing),
        "TE": base.round_float((passing + 1.0) / 2),
        "RB": base.round_float(rushing),
    }


def weather_label(temp_f, wind_mph, gust_mph, precip_probability, precip_in) -> str:
    wind = max(wind_mph or 0.0, (gust_mph or 0.0) * 0.70)
    wet = (precip_probability or 0.0) >= 60 or (precip_in or 0.0) >= 0.05
    if wind >= 20:
        return "Strong wind — passing downgrade"
    if wet and wind >= 12:
        return "Wind and precipitation — passing downgrade"
    if wet:
        return "Wet conditions — slight passing downgrade"
    if temp_f is not None and temp_f <= 20:
        return "Extreme cold — slight passing downgrade"
    if temp_f is not None and temp_f <= 32:
        return "Cold weather — small passing downgrade"
    return "Low weather impact"


def fetch_weather(row: pd.Series) -> dict:
    roof = clean_text(row.get("roof")).lower()
    if roof in PROTECTED_ROOFS:
        return {
            "available": True,
            "protected": True,
            "roof": roof,
            "label": "Indoor/roof-protected — no weather adjustment",
            "multipliers": {"QB": 1.0, "RB": 1.0, "WR": 1.0, "TE": 1.0},
            "source": "Open-Meteo",
        }

    home = base.normalize_team(row.get("home_team"))
    coords = TEAM_COORDS.get(home)
    kickoff = kickoff_utc(row)
    if not coords or kickoff is None:
        return {"available": False, "protected": False, "roof": roof, "label": "Weather forecast unavailable"}

    # Open-Meteo forecast horizon is sufficient for the next NFL game window.
    params = {
        "latitude": coords[0],
        "longitude": coords[1],
        "hourly": "temperature_2m,precipitation_probability,precipitation,wind_speed_10m,wind_gusts_10m",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "UTC",
        "forecast_days": 16,
    }
    try:
        response = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            raise ValueError("No hourly weather returned")
        parsed = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in times]
        idx = min(range(len(parsed)), key=lambda i: abs((parsed[i] - kickoff).total_seconds()))
        if abs((parsed[idx] - kickoff).total_seconds()) > 3 * 3600:
            raise ValueError("Kickoff outside forecast horizon")

        def at(key, default=0.0):
            values = hourly.get(key, [])
            return clean_number(values[idx], default) if idx < len(values) else default

        temp_f = at("temperature_2m", None)
        precip_probability = at("precipitation_probability", 0.0)
        precip_in = at("precipitation", 0.0)
        wind_mph = at("wind_speed_10m", 0.0)
        gust_mph = at("wind_gusts_10m", 0.0)
        return {
            "available": True,
            "protected": False,
            "roof": roof or "outdoors/unknown",
            "kickoff_utc": kickoff.isoformat(),
            "temperature_f": base.round_float(temp_f, 1) if temp_f is not None else None,
            "precip_probability": base.round_float(precip_probability, 0),
            "precipitation_in": base.round_float(precip_in, 2),
            "wind_mph": base.round_float(wind_mph, 1),
            "wind_gust_mph": base.round_float(gust_mph, 1),
            "label": weather_label(temp_f, wind_mph, gust_mph, precip_probability, precip_in),
            "multipliers": weather_multipliers(temp_f, wind_mph, gust_mph, precip_probability, precip_in),
            "source": "Open-Meteo",
        }
    except Exception as exc:
        return {
            "available": False,
            "protected": False,
            "roof": roof,
            "label": "Weather forecast unavailable",
            "error": str(exc)[:140],
            "multipliers": {"QB": 1.0, "RB": 1.0, "WR": 1.0, "TE": 1.0},
        }


def line_quality(total_line, implied_team_total, team_line) -> str:
    if total_line is None or implied_team_total is None:
        return "Vegas line unavailable"
    if implied_team_total >= 26:
        return "Excellent team scoring environment"
    if total_line >= 49 and abs(team_line or 0) <= 4:
        return "High-total, competitive fantasy line"
    if implied_team_total >= 24.5:
        return "Strong team scoring line"
    if total_line <= 41:
        return "Low-scoring line"
    if abs(team_line or 0) >= 9:
        return "Blowout-risk game script"
    return "Neutral fantasy line"


def market_context(row: pd.Series, team: str, schedules: pd.DataFrame) -> dict:
    spread = clean_number(row.get("spread_line"))
    total_line = clean_number(row.get("total_line"))
    line = team_spread(row, team)
    if spread is None or total_line is None or line is None:
        return {"available": False, "label": "Vegas line unavailable"}

    implied_team = total_line / 2.0 - line / 2.0
    implied_opponent = total_line - implied_team
    history = market_history(schedules, team, row.get("gameday"), line)
    return {
        "available": True,
        "team_spread": base.round_float(line, 1),
        "game_total": base.round_float(total_line, 1),
        "implied_team_total": base.round_float(implied_team, 1),
        "implied_opponent_total": base.round_float(implied_opponent, 1),
        "line_quality": line_quality(total_line, implied_team, line),
        "history": history,
        "source": "nflverse schedules",
    }


def build_game_contexts(season: int) -> dict[str, dict]:
    schedules = load_schedules()
    season_values = pd.to_numeric(schedules.get("season"), errors="coerce")
    game_type = schedules.get("game_type", pd.Series(index=schedules.index, dtype=object)).astype(str).str.upper()
    current = schedules[season_values.eq(season) & game_type.eq("REG")].copy()
    if current.empty:
        return {}

    today = datetime.now(timezone.utc).date()
    unplayed = current[
        current.get("home_score", pd.Series(index=current.index, dtype=float)).isna()
        & current.get("away_score", pd.Series(index=current.index, dtype=float)).isna()
        & current["game_date"].dt.date.ge(today - timedelta(days=1))
    ].sort_values(["game_date", "gametime", "week"])

    contexts: dict[str, dict] = {}
    weather_cache: dict[str, dict] = {}

    for _, row in unplayed.iterrows():
        home = base.normalize_team(row.get("home_team"))
        away = base.normalize_team(row.get("away_team"))
        if home not in base.TEAM_NAMES or away not in base.TEAM_NAMES:
            continue
        game_id = clean_text(row.get("game_id")) or f"{season}-{row.get('week')}-{away}-{home}"
        if game_id not in weather_cache:
            weather_cache[game_id] = fetch_weather(row)
        weather = weather_cache[game_id]

        for team, opponent, is_home in ((home, away, True), (away, home, False)):
            if team in contexts:
                continue
            market = market_context(row, team, schedules)
            contexts[team] = {
                "game_id": game_id,
                "week": int(clean_number(row.get("week"), 0) or 0),
                "gameday": clean_text(row.get("gameday")),
                "gametime_et": clean_text(row.get("gametime")),
                "home": is_home,
                "opponent": opponent,
                "opponent_name": base.TEAM_NAMES.get(opponent, opponent),
                "stadium": clean_text(row.get("stadium")),
                "roof": clean_text(row.get("roof")),
                "weather": weather,
                "market": market,
            }

    return contexts
