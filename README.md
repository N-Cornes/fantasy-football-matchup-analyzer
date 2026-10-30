# Matchup Edge — Fantasy Football Matchup Analyzer

Matchup Edge is a data-driven NFL fantasy football website that answers one question: **when two teams play, where is each defense vulnerable and which offensive players are most likely to be used to attack those weaknesses?**

## What it does

1. User selects two NFL teams.
2. The app analyzes current-season defensive performance.
3. It separates **major** and **minor** defensive weaknesses.
4. It ranks offensive players whose actual usage best matches those weaknesses.
5. It explains every recommendation with measurable usage and matchup data.

The page intentionally shows no matchup recommendations until both teams are selected.

## Data & analytics

The automated pipeline uses current-season [nflverse](https://github.com/nflverse/nflverse-data) play-by-play and weekly roster data.

Defensive signals include:
- EPA allowed per pass and rush
- yards allowed per play
- explosive pass/run rate
- touchdown rate
- sack rate
- red-zone touchdown rate
- PPR fantasy points allowed to WR, TE, and RB groups

Player-role signals include:
- target share
- rushing share
- recent four-game usage
- red-zone usage
- quarterback pass-attempt share

Recommendations combine **role strength** with **opponent vulnerability**. This is a transparent matchup model, not a guarantee of player performance.

## Tech stack

- Python / pandas / PyArrow — NFL data pipeline and feature engineering
- Vanilla JavaScript — matchup scoring in the browser
- HTML / CSS — responsive frontend
- GitHub Actions — daily data refresh and automated Pages deployment
- GitHub Pages — hosting

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python scripts/build_matchups.py
python -m http.server 8000 --directory docs
```

Open `http://localhost:8000`.

## First GitHub setup

1. Push this repository to GitHub.
2. Open **Settings → Pages** and set **Source** to **GitHub Actions**.
3. Open **Actions → Update NFL Data → Run workflow** once.
4. The generated data commit triggers the Pages deployment.
5. After that, the scheduled workflow refreshes matchup data daily during the season.

## Repository topics

Suggested GitHub topics:

`fantasy-football` `nfl` `nfl-analytics` `sports-analytics` `python` `javascript` `data-pipeline` `github-actions` `github-pages` `pandas`

## Data source

NFL analytics data is provided by the nflverse ecosystem. This repository does not redistribute official NFL branding assets and is not affiliated with the NFL.
