"""
nba/download.py
==============
Download every NBA game since 2008-09 (scores) and every sportsbook line ESPN kept for games
since 2013-14, into data/nba/. Resumable: re-running only fetches what's missing, plus the
last few days (scores and lines can still change) and the coming week.

    py nba/download.py              # everything missing (first run ~15-25 min)
    py nba/download.py --recent     # just the last 3 days + next 7 (what a site update needs)

Files:
    data/nba/events.json   {event id: game}   (see espn.parse_event)
    data/nba/dates.json    dates already fetched for good
    data/nba/odds.json     {event id: [one dict per sportsbook]}   (see espn.parse_odds_item)
"""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import espn  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "nba"
EVENTS = DIR / "events.json"
DATES = DIR / "dates.json"
ODDS = DIR / "odds.json"

FIRST_DAY = date(2008, 10, 1)        # 2008-09 season: one season of Elo burn-in before the lines start
FIRST_ODDS_SEASON = 2014             # ESPN's lines start in 2013-14
WORKERS = 6


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path, obj):
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def season_days(start, end):
    """Every date that can hold an NBA game: Oct-Jun, plus the 2020 bubble and the late 2021 Finals."""
    d = start
    while d <= end:
        if d.month not in (7, 8, 9) or (d.year == 2020) or (d.year == 2021 and d.month == 7):
            yield d
        d += timedelta(days=1)


def today_us():
    """Today's date in US Central time (ESPN files games by US date)."""
    return (datetime.now(timezone.utc) - timedelta(hours=6)).date()


def first_day():
    """Where downloading starts: 2008-09, or, when data/nba/history_scores.csv holds the past seasons (the public
    GitHub build), the day after its last game, so GitHub only ever fetches the current season."""
    hist = DIR / "history_scores.csv"
    if not hist.exists():
        return FIRST_DAY
    import csv
    with open(hist, newline="", encoding="utf-8") as fh:
        last = max((r["iso"] for r in csv.DictReader(fh)), default=None)
    if not last:
        return FIRST_DAY
    return (datetime.fromisoformat(last.replace("Z", "+00:00")) - timedelta(hours=5)).date() + timedelta(days=1)


def fetch_scores(recent_only=False, ahead=7, log=print):
    events = _load(EVENTS, {})
    done = set(_load(DATES, []))
    today = today_us()
    settled_before = today - timedelta(days=2)
    if recent_only:
        days = [today + timedelta(days=i) for i in range(-3, ahead + 1)]
    else:
        days = [d for d in season_days(first_day(), today + timedelta(days=ahead))
                if d.strftime("%Y%m%d") not in done or d > settled_before]
    log(f"scoreboards to fetch: {len(days)}")
    n = 0
    with ThreadPoolExecutor(WORKERS) as pool:
        futs = {pool.submit(espn.scoreboard, d.strftime("%Y%m%d")): d for d in days}
        for f in as_completed(futs):
            d = futs[f]
            for g in f.result():
                old = events.get(g["id"])
                if old and "dk" in old and "dk" not in g:
                    g["dk"] = old["dk"]          # keep the last pre-game DraftKings line once ESPN drops it
                events[g["id"]] = g
            if d <= settled_before:
                done.add(d.strftime("%Y%m%d"))
            n += 1
            if n % 200 == 0:
                log(f"  {n}/{len(days)} dates, {len(events)} games")
                _save(EVENTS, events)
                _save(DATES, sorted(done))
    _save(EVENTS, events)
    _save(DATES, sorted(done))
    return events


def fetch_odds(events, refresh_days=3, log=print):
    """Lines for finished games (and games in the last few days, whose closing lines may still settle)."""
    odds = _load(ODDS, {})
    cutoff = (datetime.now(timezone.utc) - timedelta(days=refresh_days)).isoformat()
    todo = [eid for eid, g in events.items()
            if g["season"] >= FIRST_ODDS_SEASON and g["state"] == "post"
            and (eid not in odds or g["date"] >= cutoff)]
    log(f"games needing lines: {len(todo)}")
    n = 0
    with ThreadPoolExecutor(WORKERS) as pool:
        futs = {pool.submit(espn.event_odds, eid): eid for eid in todo}
        for f in as_completed(futs):
            eid = futs[f]
            try:
                odds[eid] = f.result()
            except RuntimeError as e:
                log(f"  skipped {eid}: {e}")
            n += 1
            if n % 500 == 0:
                log(f"  {n}/{len(todo)} games")
                _save(ODDS, odds)
    _save(ODDS, odds)
    return odds


def main():
    recent = "--recent" in sys.argv
    t0 = datetime.now()
    events = fetch_scores(recent_only=recent)
    fetch_odds(events)
    print(f"done in {(datetime.now() - t0).seconds} s: {len(events)} games")


if __name__ == "__main__":
    main()

