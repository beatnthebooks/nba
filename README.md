# Beatn’ the Books · NBA

Every NBA game, every day: the betting market’s fair price, Kalshi and Polymarket prices, an Elo model tested
against the closing line, injuries, rest, results and power ratings.

**Site:** https://beatnthebooks.github.io/nba/ · Football: https://beatnthebooks.github.io/

Analysis only, not betting advice. The short version of the research (Method page): from 2019–20 to 2025–26 the
NBA closing line was more accurate than our Elo model in all seven seasons, and none of 47 tested signals beat it.

## How it updates

GitHub Actions (`.github/workflows/nba.yml`) rebuilds the site eight times a day from free public sources: ESPN
(scores, DraftKings lines, injury report), Kalshi and Polymarket (prices). No keys or credits. The current season’s
downloads live in the Actions cache; this repo only holds past seasons’ scores (`data/nba/history_scores.csv`), the
model settings (`results/`), and the log of every suggested bet (`data/nba/pick_log.json`, frozen at tip-off).

Run it yourself (Python 3.12, standard library only):

```
python nba/board.py          # download this season from ESPN, rebuild nba/site/data.js
python -m unittest discover -s tests
```

Then open `nba/site/index.html`.

“My bets” on this public site saves to your browser only.
