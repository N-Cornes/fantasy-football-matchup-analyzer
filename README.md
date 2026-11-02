# Matchup Edge — Fantasy Football Matchup Analyzer

Matchup Edge is a data-driven NFL fantasy football website built to answer two practical questions:

**Where is a defense vulnerable, which healthy offensive players are best positioned to exploit it, and when I am choosing between two players, who has the better start this week?**

## Live Demo

**https://n-cornes.github.io/fantasy-football-matchup-analyzer/**

## What it does

1. The user can select two NFL teams for a matchup breakdown.
2. Matchup Edge analyzes current-season defensive performance for both sides.
3. It identifies real defensive vulnerabilities using percentile-based thresholds.
4. It checks current injury and practice-report information for offensive and defensive players.
5. For real upcoming games, it adds kickoff weather and the current Vegas scoring environment.
6. It ranks healthy offensive players whose actual usage best matches the opponent's weaknesses.
7. The **Player vs. Player** tool compares two fantasy players and returns a weekly Start/Sit recommendation.
8. It shows market-trend context such as recent ATS performance, favorite/underdog history, and similar-line performance.

## Weekly Start / Sit — Player vs. Player

Enter two QB, RB, WR, or TE options and Matchup Edge compares each player's next scheduled game.

The weekly Start Score combines:

- offensive role and recent usage
- opponent defensive vulnerability by position
- current player injury availability
- offensive-line injury context
- forecast weather near kickoff
- current spread, total, implied team points, and expected game script

The result explains the factors behind the recommendation instead of returning only a player name.

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

## Weather-aware analysis

For outdoor or open-roof upcoming games, the pipeline retrieves forecast conditions near kickoff using Open-Meteo.

Weather factors include:

- temperature
- sustained wind
- wind gusts
- precipitation probability
- expected precipitation
- stadium roof protection

The adjustment is intentionally conservative. Strong wind, meaningful precipitation, and extreme cold can reduce passing-game confidence, while bad-weather game scripts can slightly favor rushing volume. Dome and closed-roof games receive no weather penalty.

## Vegas and market context

Matchup Edge uses nflverse schedule/market data when available, including:

- point spread
- game total
- implied team points
- favorite/underdog game script
- recent ATS record
- ATS performance in a similar favorite/underdog role
- ATS results near a similar point spread
- recent over/under results

The **current line and implied scoring environment** can make a small adjustment to a player's weekly fantasy score. For example, a high implied team total can improve touchdown opportunity, while expected game script can slightly favor rushing or passing volume.

Historical ATS behavior is displayed as a **trend signal only**. A team's history of covering or beating market expectations does not mean Vegas is wrong and is not treated as a guaranteed predictive edge.

## Data & analytics

The automated pipeline uses current-season data from the [nflverse](https://github.com/nflverse/nflverse-data) ecosystem, including play-by-play, weekly rosters, injury/practice reports, schedules, and available market lines. Forecast weather comes from Open-Meteo.

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

Recommendations combine **player role strength, opponent vulnerability, recent usage, injuries, weather, and the current scoring environment**.

## Tech stack

- **Python / pandas / PyArrow** — NFL data pipeline and feature engineering
- **Requests / Open-Meteo** — automated kickoff-weather context
- **Vanilla JavaScript** — matchup scoring, Start/Sit comparison, and recommendation logic in the browser
- **HTML / CSS** — responsive frontend
- **GitHub Actions** — automated NFL data refresh and site deployment
- **GitHub Pages** — hosting

## Automation

The repository includes automated workflows that:

1. download the latest available current-season nflverse data
2. fetch upcoming-game weather when applicable
3. calculate current market and historical ATS context
4. rebuild the matchup dataset
5. commit refreshed matchup data when it changes
6. deploy the latest site through GitHub Pages

The data refresh workflow is scheduled to run daily during the season and can also be triggered manually from GitHub Actions.

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

Football and market analysis is built primarily from the nflverse ecosystem. Forecast weather is supplied by Open-Meteo. Matchup Edge is not affiliated with the NFL and does not redistribute official NFL branding assets.

Matchup Edge provides data-driven fantasy recommendations and market trend context. Recommendations and historical betting trends are not guarantees of player performance or future betting results.

---

**Created by Nicholas Cornes**
