"""
nba/espn.py
===========
ESPN's free public NBA endpoints (no key): the daily scoreboard (scores, tip times, and
DraftKings' current line for upcoming games), each game's odds history from the "core" API
(several books, with opening and closing prices since about 2023-24), and the injury report.

Teams are keyed by ESPN team id (1-30), which stays the same when a franchise moves or renames
(New Jersey -> Brooklyn Nets is id 17 throughout). `CODE` gives today's abbreviation.

Standard library only.
"""

from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}

# ESPN team id -> current abbreviation, city, nickname, primary color
TEAMS = {
    1: ("ATL", "Atlanta", "Hawks", "c8102e"), 2: ("BOS", "Boston", "Celtics", "008348"),
    3: ("NO", "New Orleans", "Pelicans", "0a2240"), 4: ("CHI", "Chicago", "Bulls", "ce1141"),
    5: ("CLE", "Cleveland", "Cavaliers", "860038"), 6: ("DAL", "Dallas", "Mavericks", "0064b1"),
    7: ("DEN", "Denver", "Nuggets", "0e2240"), 8: ("DET", "Detroit", "Pistons", "1d428a"),
    9: ("GS", "Golden State", "Warriors", "1d428a"), 10: ("HOU", "Houston", "Rockets", "ce1141"),
    11: ("IND", "Indiana", "Pacers", "002d62"), 12: ("LAC", "LA", "Clippers", "1d428a"),
    13: ("LAL", "Los Angeles", "Lakers", "552583"), 14: ("MIA", "Miami", "Heat", "98002e"),
    15: ("MIL", "Milwaukee", "Bucks", "00471b"), 16: ("MIN", "Minnesota", "Timberwolves", "266092"),
    17: ("BKN", "Brooklyn", "Nets", "3a3a3a"), 18: ("NY", "New York", "Knicks", "1d428a"),
    19: ("ORL", "Orlando", "Magic", "0077c0"), 20: ("PHI", "Philadelphia", "76ers", "1d428a"),
    21: ("PHX", "Phoenix", "Suns", "29127a"), 22: ("POR", "Portland", "Trail Blazers", "e03a3e"),
    23: ("SAC", "Sacramento", "Kings", "5a2d81"), 24: ("SA", "San Antonio", "Spurs", "8a8d8f"),
    25: ("OKC", "Oklahoma City", "Thunder", "007ac1"), 26: ("UTAH", "Utah", "Jazz", "4e008e"),
    27: ("WSH", "Washington", "Wizards", "e31837"), 28: ("TOR", "Toronto", "Raptors", "ce1141"),
    29: ("MEM", "Memphis", "Grizzlies", "5d76a9"), 30: ("CHA", "Charlotte", "Hornets", "1d1160"),
}
CODE = {tid: t[0] for tid, t in TEAMS.items()}
ID_BY_CODE = {t[0]: tid for tid, t in TEAMS.items()}

# Season types ESPN uses: 1 preseason, 2 regular season, 3 playoffs, 5 play-in
KEEP_TYPES = {2, 3, 5}


def get_json(url, tries=4, timeout=30, gz=False):
    """GET a JSON document; retries on network errors and 5xx/429 with backoff. gz=True asks for a gzipped
    response (game summaries are ~400 KB plain, ~40 KB gzipped)."""
    last = None
    headers = dict(UA, **({"Accept-Encoding": "gzip"} if gz else {}))
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return json.loads(body)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (400, 404):
                return None
        except Exception as e:  # noqa: BLE001 (timeouts, resets)
            last = e
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"ESPN request failed: {url}: {last!r}")


# ----------------------------------------------------------------------
# Scoreboard
# ----------------------------------------------------------------------

def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_event(ev):
    """One scoreboard event -> compact dict, or None for games we don't track
    (preseason, All-Star, exhibitions against non-NBA teams)."""
    stype = ev.get("season", {}).get("type")
    c = ev["competitions"][0]
    teams = {}
    for t in c["competitors"]:
        tid = int(t["team"]["id"])
        if tid not in TEAMS:
            return None
        teams[t["homeAway"]] = (tid, t)
    if stype not in KEEP_TYPES or set(teams) != {"home", "away"}:
        return None
    st = c["status"]["type"]
    done = bool(st.get("completed"))
    (hid, ht), (aid, at) = teams["home"], teams["away"]
    notes = [n.get("headline", "") for n in c.get("notes", []) if n.get("headline")]
    out = {
        "id": ev["id"], "date": ev["date"], "season": ev["season"]["year"], "stype": stype,
        "ctype": (c.get("type") or {}).get("abbreviation", ""),
        "neutral": bool(c.get("neutralSite")),
        "city": ((c.get("venue") or {}).get("address") or {}).get("city", ""),
        "venue": (c.get("venue") or {}).get("fullName", ""),
        "home": hid, "away": aid,
        "hs": _num(ht.get("score")) if done else None,
        "as": _num(at.get("score")) if done else None,
        "state": st.get("state"),            # pre / in / post
        "status": st.get("name"),            # STATUS_FINAL, STATUS_POSTPONED, ...
        "detail": st.get("shortDetail", ""),
        "periods": c["status"].get("period"),
        "notes": notes,
    }
    odds = c.get("odds") or []
    if odds:
        dk = parse_scoreboard_odds(odds[0])
        if dk:
            out["dk"] = dk
    return out


def parse_scoreboard_odds(o):
    """The scoreboard's own odds block (DraftKings, current + opening) -> {hml, aml, sp, hso, aso, tot, oo, uo, o: {...}}.
    'close' in this block is the CURRENT price until tip-off."""
    def num(x):
        try:
            return float(str(x).lstrip("ou").replace("+", "")) if x not in (None, "", "OFF") else None
        except ValueError:
            return 100.0 if str(x).upper() == "EVEN" else None

    def snap(which):
        ml, ps, tt = o.get("moneyline") or {}, o.get("pointSpread") or {}, o.get("total") or {}
        g = lambda blk, side, key: num(((blk.get(side) or {}).get(which) or {}).get(key))  # noqa: E731
        s = {"hml": g(ml, "home", "odds"), "aml": g(ml, "away", "odds"),
             "sp": g(ps, "home", "line"), "hso": g(ps, "home", "odds"), "aso": g(ps, "away", "odds"),
             "tot": g(tt, "over", "line"), "oo": g(tt, "over", "odds"), "uo": g(tt, "under", "odds")}
        return {k: v for k, v in s.items() if v is not None}

    cur = snap("close")
    if not cur:
        cur = {k: v for k, v in (("sp", _num(o.get("spread"))), ("tot", _num(o.get("overUnder")))) if v is not None}
    if not cur:
        return None
    cur["p"] = ((o.get("provider") or {}).get("name")) or "DraftKings"
    opn = snap("open")
    if opn:
        cur["o"] = opn
    return cur


def scoreboard(day):
    """Games on one date (YYYYMMDD, US calendar day as ESPN files it)."""
    d = get_json(f"{SITE}/scoreboard?dates={day}&limit=100")
    if not d:
        return []
    return [g for g in (parse_event(ev) for ev in d.get("events", [])) if g]


# ----------------------------------------------------------------------
# Odds (core API): one item per sportsbook
# ----------------------------------------------------------------------

def _am(block, *path):
    """American odds or line from nested open/close/current blocks, as float."""
    x = block
    for p in path:
        if not isinstance(x, dict):
            return None
        x = x.get(p)
    if isinstance(x, dict):
        x = x.get("american", x.get("alternateDisplayValue"))
    if x in (None, "", "OFF", "EVEN"):
        return 100.0 if x == "EVEN" else None
    try:
        return float(str(x).replace("+", ""))
    except ValueError:
        return None


def _snap(item, which):
    """Opening or closing snapshot {hml, aml, hsp, hso, aso, tot, oo, uo} if the book has one."""
    h, a = item.get("homeTeamOdds") or {}, item.get("awayTeamOdds") or {}
    if which not in h and which not in a and which not in item:
        return None
    s = {"hml": _am(h, which, "moneyLine"), "aml": _am(a, which, "moneyLine"),
         "hsp": _am(h, which, "pointSpread"), "hso": _am(h, which, "spread"), "aso": _am(a, which, "spread"),
         "tot": _am(item, which, "total"), "oo": _am(item, which, "over"), "uo": _am(item, which, "under")}
    return {k: v for k, v in s.items() if v is not None} or None


def parse_odds_item(it):
    h, a = it.get("homeTeamOdds") or {}, it.get("awayTeamOdds") or {}
    prov = it.get("provider") or {}
    rec = {"p": prov.get("name", ""), "pid": prov.get("id"),
           "sp": _num(it.get("spread")), "tot": _num(it.get("overUnder")),
           "oo": _num(it.get("overOdds")), "uo": _num(it.get("underOdds")),
           "hml": _num(h.get("moneyLine")), "aml": _num(a.get("moneyLine")),
           "hso": _num(h.get("spreadOdds")), "aso": _num(a.get("spreadOdds")),
           "isp": _num(it.get("initialSpread")), "itot": _num(it.get("initialOverUnder"))}
    for which, key in (("open", "o"), ("close", "c")):
        s = _snap(it, which)
        if s:
            rec[key] = s
    return {k: v for k, v in rec.items() if v is not None}


def event_odds(eid):
    """Every sportsbook ESPN has for one game (list of compact dicts; [] if none)."""
    d = get_json(f"{CORE}/events/{eid}/competitions/{eid}/odds?limit=50")
    if not d:
        return []
    return [parse_odds_item(it) for it in d.get("items", [])]


# ----------------------------------------------------------------------
# Box scores (site summary endpoint): one compact row per player
# ----------------------------------------------------------------------

# Row layout (players.py relies on it): pid, minutes, starter, +/-, then the box line. Players who were active but
# didn't play are a short row [pid, 0, starter]. Inactive (injured, suspended) players aren't in ESPN's box score.
BOX_COLS = ("pid", "min", "starter", "pm", "pts", "fgm", "fga", "tpm", "tpa", "ftm", "fta",
            "oreb", "dreb", "ast", "stl", "blk", "tov", "pf")
_BOX_KEYS = {"minutes": ["min"], "plusMinus": ["pm"], "points": ["pts"],
             "fieldGoalsMade-fieldGoalsAttempted": ["fgm", "fga"],
             "threePointFieldGoalsMade-threePointFieldGoalsAttempted": ["tpm", "tpa"],
             "freeThrowsMade-freeThrowsAttempted": ["ftm", "fta"],
             "offensiveRebounds": ["oreb"], "defensiveRebounds": ["dreb"], "assists": ["ast"], "steals": ["stl"],
             "blocks": ["blk"], "turnovers": ["tov"], "fouls": ["pf"]}


def _box_num(x):
    try:
        return float(str(x).replace("+", ""))
    except (TypeError, ValueError):
        return None


def parse_box(d) -> tuple[dict, dict]:
    """A game summary -> ({team id (str): [rows]}, {pid: [name, position]}). Empty dicts if ESPN has no box score."""
    teams, names = {}, {}
    for team in ((d or {}).get("boxscore") or {}).get("players") or []:
        tid = str((team.get("team") or {}).get("id", ""))
        rows = []
        for grp in team.get("statistics") or []:
            keys = grp.get("keys") or []
            for a in grp.get("athletes") or []:
                ath = a.get("athlete") or {}
                try:
                    pid = int(ath["id"])
                except (KeyError, TypeError, ValueError):
                    continue
                names[pid] = [ath.get("displayName", ""), ((ath.get("position") or {}).get("abbreviation")) or ""]
                st = 1 if a.get("starter") else 0
                vals = {}
                for k, v in zip(keys, a.get("stats") or []):
                    cols = _BOX_KEYS.get(k)
                    if not cols:
                        continue
                    parts = str(v).split("-", 1) if len(cols) == 2 else [v]
                    for c, p in zip(cols, parts):
                        vals[c] = _box_num(p)
                mins = vals.get("min") or 0.0
                if a.get("didNotPlay") or mins <= 0:
                    rows.append([pid, 0, st])
                    continue
                rows.append([pid, mins, st] + [vals.get(c) for c in BOX_COLS[3:]])
        if rows:
            teams[tid] = rows
    return teams, names


def boxscore(eid):
    """One game's box score: ({team id: rows}, {pid: [name, pos]})."""
    return parse_box(get_json(f"{SITE}/summary?event={eid}", gz=True))


# ----------------------------------------------------------------------
# Injuries
# ----------------------------------------------------------------------

def injuries():
    """{team id: [{name, pos, status, date, comment}]} from ESPN's live injury report."""
    d = get_json(f"{SITE}/injuries")
    out = {}
    for team in (d or {}).get("injuries", []):
        try:
            tid = int(team["id"])
        except (KeyError, ValueError):
            continue
        rows = []
        for x in team.get("injuries", []):
            ath = x.get("athlete") or {}
            rows.append({"name": ath.get("displayName") or " ".join(
                             filter(None, (ath.get("firstName"), ath.get("lastName")))),
                         "pid": str((ath.get("links") or [{}])[0].get("href", "")).rsplit("/id/", 1)[-1].split("/")[0]
                         if ath.get("links") else None,
                         "pos": ((ath.get("position") or {}).get("abbreviation")) or "",
                         "status": x.get("status", ""), "date": x.get("date", ""),
                         "comment": x.get("shortComment", "")})
        out[tid] = rows
    return out
