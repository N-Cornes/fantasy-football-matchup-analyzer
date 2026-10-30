# Matchup Edge — Fantasy Football Matchup Analyzer

Matchup Edge is a data-driven NFL fantasy football website built to answer one practical question:

**When two teams play, where is each defense vulnerable and which healthy offensive players are best positioned to exploit those weaknesses?**

## Live Demo

**https://n-cornes.github.io/fantasy-football-matchup-analyzer/**

## What it does

1. The user selects two NFL teams.
2. Matchup Edge analyzes current-season defensive performance for both sides.
3. It identifies real defensive vulnerabilities using percentile-based thresholds.
4. It checks current injury and practice-report information for offensive and defensive players.
5. It ranks healthy offensive players whose actual usage best matches the opponent's weaknesses.
6. It explains each recommendation with measurable matchup, usage, and injury context.

The page intentionally shows no matchup recommendations until two different teams are selected.

## Weakness model

Defensive weakness scores are ranked against the rest of the NFL.

- **Major weakness:** 75th percentile or higher vulnerability
- **Minor weakness:** 60th–74th percentile vulnerability
- Below the 60th percentile is not presented as a defensive weakness

This keeps average matchups from being labeled as exploitable weaknesses.

## Injury-aware analysis

Matchup Edge combines season performance with the latest nflverse injury and practice-report data available to the pipeline.

The model can account for:

- OUT, doubtful, questionable, and practice-participation designations
- IR/reserve status when determining whether a fantasy player should be recommended
- offensive-line injuries that may reduce QB/RB confidence
- defensive secondary injuries that can increase WR/pass vulnerability
- linebacker and defensive-line injuries that can affect RB, TE, run, and red-zone matchups
- projected opportunity increases when an injured player's workload may shift to healthy teammates

Long-term defensive absences are not double-counted on top of season statistics.

## Data & analytics

The automated pipeline uses current-season data from the [nflverse](https://github.com/nflverse/nflverse-data) ecosystem, including play-by-play, weekly rosters, and injury/practice reports.

Defensive signals include:

- EPA allowed per pass and rush
- yards allowed per play
- explosive pass and run rate
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
- injury-adjusted availability
- projected opportunity shifts caused by teammate injuries

Recommendations combine **player role strength, opponent vulnerability, recent usage, and injury context**.

## Tech stack

- **Python / pandas / PyArrow** — NFL data pipeline and feature engineering
- **Vanilla JavaScript** — matchup scoring and recommendation logic in the browser
- **HTML / CSS** — responsive frontend
- **GitHub Actions** — automated NFL data refresh and site deployment
- **GitHub Pages** — hosting

## Automation

The repository includes automated workflows that:

1. download the latest available current-season nflverse data
2. rebuild the matchup dataset
3. commit refreshed matchup data when it changes
4. deploy the latest site through GitHub Pages

The NFL data refresh workflow is scheduled to run daily during the season and can also be triggered manually from GitHub Actions.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python scripts/build_matchups_v2.py
python -m http.server 8000 --directory docs
```

Open `http://localhost:8000` in a browser.

## Repository topics

Suggested GitHub topics:

`fantasy-football` `nfl` `nfl-analytics` `sports-analytics` `python` `javascript` `data-pipeline` `github-actions` `github-pages` `pandas`

## Data source and disclaimer

All football data analysis is built from the nflverse ecosystem. Matchup Edge is not affiliated with the NFL and does not redistribute official NFL branding assets.

Matchup Edge provides matchup recommendations based on available data. Recommendations are not guarantees of player performance.

---

**Created by Nicholas Cornes**
