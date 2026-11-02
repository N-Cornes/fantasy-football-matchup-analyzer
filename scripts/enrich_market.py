from __future__ import annotations

import json

import pandas as pd

import build_matchups as base

SCHEDULE_URL = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet"


def clean_number(value, default=None):
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def american_implied_probability(moneyline):
    ml = clean_number(moneyline)
    if ml is None or ml == 0:
        return None
    if ml < 0:
        return (-ml) / ((-ml) + 100.0)
    return 100.0 / (ml + 100.0)


def no_vig_probability(team_moneyline, opponent_moneyline):
    team_raw = american_implied_probability(team_moneyline)
    opponent_raw = american_implied_probability(opponent_moneyline)
    if team_raw is None:
        return None
    if opponent_raw is None:
        return team_raw
    total = team_raw + opponent_raw
    if total <= 0:
        return team_raw
    return team_raw / total


def team_moneylines(row: pd.Series, team: str):
    home = base.normalize_team(row.get("home_team"))
    if team == home:
        return clean_number(row.get("home_moneyline")), clean_number(row.get("away_moneyline"))
    return clean_number(row.get("away_moneyline")), clean_number(row.get("home_moneyline"))


def chance_label(probability):
    if probability is None:
        return "Moneyline chance unavailable"
    if probability >= 0.65:
        return "Strong market favorite"
    if probability >= 0.55:
        return "Market favorite"
    if probability >= 0.45:
        return "Near toss-up"
    if probability >= 0.35:
        return "Live market underdog"
    return "Heavy market underdog"


def main():
    if not base.OUTPUT.exists():
        raise FileNotFoundError(f"Missing generated matchup data: {base.OUTPUT}")

    payload = json.loads(base.OUTPUT.read_text(encoding="utf-8"))
    schedules = base.download_parquet(SCHEDULE_URL).copy()
    for col in ("home_team", "away_team"):
        if col in schedules.columns:
            schedules[col] = schedules[col].map(base.normalize_team)

    if "game_id" not in schedules.columns:
        raise KeyError("nflverse schedules data is missing game_id")

    by_game = schedules.dropna(subset=["game_id"]).drop_duplicates("game_id", keep="last").set_index("game_id")
    enriched = 0

    for team, profile in payload.get("teams", {}).items():
        context = profile.get("week_context") or {}
        game_id = str(context.get("game_id") or "")
        market = context.get("market") or {}
        if not game_id or game_id not in by_game.index:
            continue

        row = by_game.loc[game_id]
        team_ml, opponent_ml = team_moneylines(row, team)
        raw_probability = american_implied_probability(team_ml)
        fair_probability = no_vig_probability(team_ml, opponent_ml)

        market["moneyline"] = base.round_float(team_ml, 0) if team_ml is not None else None
        market["opponent_moneyline"] = base.round_float(opponent_ml, 0) if opponent_ml is not None else None
        market["raw_implied_win_probability"] = base.round_float(raw_probability, 4) if raw_probability is not None else None
        market["market_win_probability"] = base.round_float(fair_probability, 4) if fair_probability is not None else None
        market["chance_label"] = chance_label(fair_probability)
        market["moneyline_source"] = "nflverse schedules"
        context["market"] = market
        profile["week_context"] = context
        enriched += 1

    meta = payload.setdefault("meta", {})
    meta["model_version"] = "1.3.0"
    meta["market_note"] = (
        "Current spread, total, implied points, moneyline and no-vig moneyline win chance are included when available. "
        "Historical ATS results are a small contextual signal, not a guarantee. Player comparison uses team/game market context; "
        "player-specific prop hit rates require a separate prop-odds source."
    )

    base.OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Added moneyline context for {enriched} team-week records")


if __name__ == "__main__":
    main()
