"""
nba/games.py
============
Turn the raw ESPN downloads (data/nba/events.json + odds.json, from history.py) into one list of games,
oldest first, with everything known BEFORE tip-off:

  * consensus closing lines across sportsbooks: moneyline (no-vig fair chance = median over books; price =
    median decimal odds per side), spread (median home line, odds at that line), total (same)
  * opening lines where ESPN kept them (2023-24 on, plus "initial" lines for some older books)
  * rest: days since each team's last game (1 = second night of a back-to-back), 3 games in 4 nights,
    time zones crossed since the last game

Season = ESPN's year, i.e. the year the season ENDS (2026 = 2025-26, 2027 = 2026-27).
Standard library only.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import espn

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "nba"

# Not sportsbooks: in-game prices, ESPN's "Opening" placeholder, and projection / consensus sites
NOT_BOOKS = ("live odds", "opening", "consensus", "accuscore", "numberfire", "teamrankings")

# Home arena time zone, hours vs Eastern
TZ = {**{t: 0 for t in (1, 2, 5, 8, 11, 14, 17, 18, 19, 20, 27, 28, 30)},
      **{t: -1 for t in (3, 4, 6, 10, 15, 16, 24, 25, 29)},
      7: -2, 26: -2, 21: -2,                     # Denver, Utah; Phoenix (Mountain, no DST: call it -2)
      **{t: -3 for t in (9, 12, 13, 22, 23)}}
ALTITUDE = {7, 26}                               # Denver, Salt Lake City
NEUTRAL_TZ = {"Mexico City": -1, "London": 5, "Paris": 6, "Berlin": 6, "Las Vegas": -3, "Abu Dhabi": 9}


def _load(name, default):
    try:
        return json.loads((DIR / name).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def am_to_dec(am: float) -> float:
    return 1 + am / 100 if am > 0 else 1 + 100 / -am


def dec_to_am(d: float) -> int:
    return round((d - 1) * 100) if d >= 2 else round(-100 / (d - 1))


def devig(a: float, b: float) -> float:
    """Two American prices -> fair chance of side a (multiplicative)."""
    qa, qb = 1 / am_to_dec(a), 1 / am_to_dec(b)
    return qa / (qa + qb)


def _ok_am(x):
    return x is not None and abs(x) >= 100 and abs(x) < 50000


def us_date(iso: str) -> date:
    """ESPN times are UTC; NBA games are afternoon/evening US time, so UTC-5 gives the US calendar day."""
    return (datetime.fromisoformat(iso.replace("Z", "+00:00")) - timedelta(hours=5)).date()


def central(iso: str) -> datetime:
    """Tip-off in US Central time (naive), with US daylight saving rules."""
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    y = t.year
    mar = datetime(y, 3, 8 + (6 - date(y, 3, 8).weekday()) % 7, 8, tzinfo=timezone.utc)     # 2 AM CST
    nov = datetime(y, 11, 1 + (6 - date(y, 11, 1).weekday()) % 7, 7, tzinfo=timezone.utc)  # 2 AM CDT
    off = 5 if mar <= t < nov else 6
    return (t - timedelta(hours=off)).replace(tzinfo=None)


# ----------------------------------------------------------------------
# Consensus lines
# ----------------------------------------------------------------------

def _books(items):
    return [b for b in items if not any(w in b.get("p", "").lower() for w in NOT_BOOKS)]


def _snap(b: dict, which: str) -> dict:
    """A book's closing ('c') or opening ('o') numbers, in the shape {hml, aml, sp, hso, aso, tot, oo, uo}.
    Books without explicit snapshots: their listed numbers are the last before tip-off (closing), and
    initialSpread / initialOverUnder are the opener."""
    if which == "c":
        s = b.get("c") or {}
        out = {"hml": s.get("hml", b.get("hml")), "aml": s.get("aml", b.get("aml")),
               "sp": s.get("hsp", b.get("sp")), "hso": s.get("hso", b.get("hso")), "aso": s.get("aso", b.get("aso")),
               "tot": s.get("tot", b.get("tot")), "oo": s.get("oo", b.get("oo")), "uo": s.get("uo", b.get("uo"))}
    else:
        s = b.get("o") or {}
        out = {"hml": s.get("hml"), "aml": s.get("aml"), "sp": s.get("hsp", b.get("isp")),
               "hso": s.get("hso"), "aso": s.get("aso"), "tot": s.get("tot", b.get("itot")),
               "oo": s.get("oo"), "uo": s.get("uo")}
    return out


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _half(x):
    """Round a median line to the nearest half point (books post halves)."""
    return None if x is None else round(x * 2) / 2


def consensus(items: list, which: str = "c") -> dict:
    """Median lines across sportsbooks. Books whose spread is > 3 points or total > 6 points from the
    median are dropped as stale or mis-keyed (ESPN has a few)."""
    snaps = [_snap(b, which) for b in _books(items)]
    out = {}
    sp0 = _median([s["sp"] for s in snaps])
    tt0 = _median([s["tot"] for s in snaps])
    good = [s for s in snaps if (sp0 is None or s["sp"] is None or abs(s["sp"] - sp0) <= 3)
            and (tt0 is None or s["tot"] is None or abs(s["tot"] - tt0) <= 6)]
    mls = [s for s in good if _ok_am(s["hml"]) and _ok_am(s["aml"])
           and 1.0 < 1 / am_to_dec(s["hml"]) + 1 / am_to_dec(s["aml"]) < 1.12]
    if mls:
        out["pml"] = statistics.median(devig(s["hml"], s["aml"]) for s in mls)
        out["hml"] = dec_to_am(statistics.median(am_to_dec(s["hml"]) for s in mls))
        out["aml"] = dec_to_am(statistics.median(am_to_dec(s["aml"]) for s in mls))
    sps = [s for s in good if s["sp"] is not None]
    if sps:
        line = _half(statistics.median(s["sp"] for s in sps))
        at = [s for s in sps if s["sp"] == line and _ok_am(s["hso"]) and _ok_am(s["aso"])]
        out["sp"] = line
        out["hso"] = dec_to_am(statistics.median(am_to_dec(s["hso"]) for s in at)) if at else -110
        out["aso"] = dec_to_am(statistics.median(am_to_dec(s["aso"]) for s in at)) if at else -110
    tts = [s for s in good if s["tot"] is not None and s["tot"] > 120]
    if tts:
        line = _half(statistics.median(s["tot"] for s in tts))
        at = [s for s in tts if s["tot"] == line and _ok_am(s["oo"]) and _ok_am(s["uo"])]
        out["tot"] = line
        out["oo"] = dec_to_am(statistics.median(am_to_dec(s["oo"]) for s in at)) if at else -110
        out["uo"] = dec_to_am(statistics.median(am_to_dec(s["uo"]) for s in at)) if at else -110
    out["books"] = len(good)
    return out


# ----------------------------------------------------------------------
# Games
# ----------------------------------------------------------------------

HISTORY = DIR / "history_scores.csv"     # past seasons' results only (no betting lines): what the public repo carries
HISTORY_FIELDS = ("gid", "season", "stype", "iso", "home", "away", "hs", "as", "neutral", "city", "venue", "periods")


def export_scores(before_season: int, path=HISTORY) -> int:
    """Write every played game of seasons before `before_season` from data/nba/events.json to a small CSV. The public
    GitHub build runs the Elo over it, so GitHub never needs the raw sportsbook history (that stays on the PC)."""
    import csv
    events = _load("events.json", {})
    rows = [e for e in events.values() if e["season"] < before_season and e["state"] == "post" and e["hs"] is not None]
    rows.sort(key=lambda e: (e["date"], e["id"]))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HISTORY_FIELDS)
        for e in rows:
            w.writerow([e["id"], e["season"], e["stype"], e["date"], e["home"], e["away"], int(e["hs"]), int(e["as"]),
                        int(bool(e["neutral"])), e.get("city", ""), e.get("venue", ""), e.get("periods") or 4])
    return len(rows)


def _history_events() -> dict:
    """history_scores.csv rows in the shape of download.py's events (finished games, no lines)."""
    import csv
    if not HISTORY.exists():
        return {}
    out = {}
    with open(HISTORY, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["gid"]] = {"id": r["gid"], "date": r["iso"], "season": int(r["season"]), "stype": int(r["stype"]),
                             "ctype": "STD", "neutral": r["neutral"] == "1", "city": r["city"], "venue": r["venue"],
                             "home": int(r["home"]), "away": int(r["away"]), "hs": float(r["hs"]), "as": float(r["as"]),
                             "state": "post", "status": "STATUS_FINAL", "detail": "Final", "periods": int(r["periods"]),
                             "notes": []}
    return out


def load(events=None, odds=None) -> list:
    """Every tracked game (regular season, play-in, playoffs), oldest first, with closing lines, rest and travel.
    Postponed/cancelled games that were never played are dropped unless still upcoming. Past seasons missing from
    events.json (the GitHub build only downloads the current season) come from history_scores.csv, without lines."""
    if events is None:
        events = {**_history_events(), **_load("events.json", {})}
    odds = _load("odds.json", {}) if odds is None else odds
    games = []
    for eid, e in events.items():
        st = e.get("status", "")
        if st in ("STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_CANCELLED") or (e["state"] == "post" and e["hs"] is None):
            continue
        g = {"gid": eid, "season": e["season"], "stype": e["stype"], "playoff": e["stype"] in (3, 5),
             "iso": e["date"], "day": us_date(e["date"]), "home": e["home"], "away": e["away"],
             "hcode": espn.CODE[e["home"]], "acode": espn.CODE[e["away"]],
             "neutral": e["neutral"], "city": e.get("city", ""), "venue": e.get("venue", ""),
             "cup_final": e.get("ctype") not in ("STD", "", None) and e["neutral"],
             "hs": e["hs"], "as": e["as"], "state": e["state"], "detail": e.get("detail", ""),
             "notes": e.get("notes", []), "ot": (e.get("periods") or 0) > 4 and e["state"] == "post"}
        items = odds.get(eid)
        close = consensus(items, "c") if items else {}
        if not close.get("books") and e.get("dk"):          # upcoming (or no core lines): ESPN's DraftKings line
            dk = e["dk"]
            close = {k: dk[k] for k in ("hml", "aml", "sp", "hso", "aso", "tot", "oo", "uo") if dk.get(k) is not None}
            if _ok_am(close.get("hml")) and _ok_am(close.get("aml")):
                close["pml"] = devig(close["hml"], close["aml"])
            close["books"] = 1
            close["src"] = "dk"
        g["line"] = close
        g["open"] = consensus(items, "o") if items else {}
        if not g["open"].get("books") and e.get("dk", {}).get("o"):
            o = e["dk"]["o"]
            g["open"] = {k: o[k] for k in ("hml", "aml", "sp", "tot") if o.get(k) is not None}
        games.append(g)
    games.sort(key=lambda g: (g["iso"], g["gid"]))
    add_schedule_features(games)
    return games


def game_tz(g) -> float:
    if g["neutral"]:
        return NEUTRAL_TZ.get(g["city"], TZ[g["home"]])
    return TZ[g["home"]]


def add_schedule_features(games: list) -> None:
    """Rest days, back-to-backs, 3-in-4, time zones crossed, games this season, home stand / road trip length.
    Uses only earlier games (by date), so it is known before tip-off."""
    last = {}                               # team -> (day, tz, season)
    recent = defaultdict(list)              # team -> days of recent games
    streak = {}                             # team -> (home?, count)
    played = defaultdict(int)               # (team, season) -> games so far
    for g in games:
        for side, t in (("h", g["home"]), ("a", g["away"])):
            prev = last.get(t)
            if prev and prev[2] == g["season"]:
                rest = (g["day"] - prev[0]).days
                tzc = abs(game_tz(g) - prev[1])
            else:
                rest, tzc = 7, 0.0
            g[side + "rest"] = min(rest, 7)
            g[side + "b2b"] = rest == 1
            ds = [d for d in recent[t] if (g["day"] - d).days <= 3]
            g[side + "3in4"] = len(ds) >= 2              # this game is the 3rd in 4 nights
            g[side + "tz"] = tzc
            g[side + "n"] = played[(t, g["season"])]
            at_home = (side == "h") and not g["neutral"]
            s = streak.get(t)
            g[side + "trip"] = (s[1] + 1) if s and s[0] == at_home and prev and prev[2] == g["season"] else 1
        for side, t in (("h", g["home"]), ("a", g["away"])):
            last[t] = (g["day"], game_tz(g), g["season"])
            recent[t] = [d for d in recent[t] if (g["day"] - d).days <= 3] + [g["day"]]
            at_home = (side == "h") and not g["neutral"]
            s = streak.get(t)
            streak[t] = (at_home, (s[1] + 1) if s and s[0] == at_home else 1)
            played[(t, g["season"])] += 1


if __name__ == "__main__":
    gs = load()
    by = defaultdict(lambda: [0, 0, 0, 0])
    for g in gs:
        b = by[g["season"]]
        b[0] += 1
        b[1] += g["hs"] is not None
        b[2] += "pml" in g["line"]
        b[3] += "sp" in g["line"]
    for s in sorted(by):
        n, done, ml, sp = by[s]
        print(f"{s - 1}-{str(s)[2:]}: {n} games, {done} played, moneyline {ml}, spread {sp}")
    print("b2b share:", sum(g["hb2b"] + g["ab2b"] for g in gs) / (2 * len(gs)))
