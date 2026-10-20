"""
nba/markets.py
==============
Live prices for upcoming NBA games, all free and keyless:

  * DraftKings' current moneyline, spread and total (ESPN's scoreboard, via games.load: g["line"] with src "dk")
  * Kalshi: KXNBAGAME (one market per team), KXNBASPREAD ("<team> wins by over X points", a ladder of lines) and
    KXNBATOTAL ("Over X points", a ladder). A spread or total bet is priced from the rung at the sportsbook line:
    YES = that team covers / the over, NO (1 - yes bid) = the other side.
  * Polymarket: series "nba-2026" (id 10345): per game a moneyline, several spreads and several totals.

shop(games) returns, per upcoming game, the same shape the NFL site uses (odds.summarize):
    {"books": 1, "fair": {"home", "spreadPoint", "spreadHome", "totalPoint", "over"},
     "ml"|"spread"|"total": {side: best offer {book, key, cents, fee, dec, point, ev}}}
"fair" = the MIDDLE of DraftKings' no-vig price, Kalshi's mid and Polymarket's mid at the same line (any that
exist). One sportsbook alone is a shaky fair price; the two exchanges were within about 1 win-% point of the
sportsbooks' close in the NFL test (exchanges.py Q1), so the median of the three is steadier than any one.

Standard library only.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import espn  # noqa: E402
import games as G  # noqa: E402

KX = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA = "https://gamma-api.polymarket.com"
POLY_SERIES = "10345"                    # "nba-2026": the 2026-27 season's games
FEE = {"kalshi": 0.07, "polymarket": 0.05}   # taker fee per $1 contract = rate x p x (1 - p) (same as the NFL site)
MAX_SPREAD = 0.06                        # wider bid-ask = too thin to quote
TITLE = {"kalshi": "Kalshi", "polymarket": "Polymarket"}
# Kalshi team codes -> ESPN team id
KX_CODE = {"ATL": 1, "BOS": 2, "NOP": 3, "NO": 3, "CHI": 4, "CLE": 5, "DAL": 6, "DEN": 7, "DET": 8, "GSW": 9, "GS": 9,
           "HOU": 10, "IND": 11, "LAC": 12, "LAL": 13, "MIA": 14, "MIL": 15, "MIN": 16, "BKN": 17, "BRK": 17,
           "NYK": 18, "NY": 18, "ORL": 19, "PHI": 20, "PHX": 21, "PHO": 21, "POR": 22, "SAC": 23, "SAS": 24, "SA": 24,
           "OKC": 25, "UTA": 26, "UTAH": 26, "WAS": 27, "WSH": 27, "TOR": 28, "MEM": 29, "CHA": 30, "CHO": 30}
NICK = {t[2]: tid for tid, t in espn.TEAMS.items()} | {"Blazers": 22, "Sixers": 20}
MONTHS = {m: i for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV",
                                      "DEC"), start=1)}
# Kalshi web pages: kalshi.com/markets/<series>/<page>/<event> (pages checked Oct 20 2026 by following kalshi.com's own
# redirects). A wrong or closed event silently opens the series' first game, so links are only built for open events.
KX_WEB = {"KXNBAGAME": "nba-game", "KXNBASPREAD": "nba-spread", "KXNBATOTAL": "nba-total"}
KX_KIND = {"KXNBAGAME": "ml", "KXNBASPREAD": "spread", "KXNBATOTAL": "total"}


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "beatnthebooks/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fee(p: float, venue: str) -> float:
    return FEE.get(venue, 0.0) * p * (1 - p)


def offer(venue: str, ask: float, point=None) -> dict:
    """An ask (dollars per $1 contract) as an offer, fee included."""
    f = fee(ask, venue)
    raw = 1 / ask
    return {"book": TITLE[venue], "key": venue, "price": round((raw - 1) * 100 if raw >= 2 else -100 / (raw - 1)),
            "point": point, "cents": round(ask * 100, 1), "fee": round(f * 100, 2), "dec": round(1 / (ask + f), 4)}


# ----------------------------------------------------------------------
# Kalshi
# ----------------------------------------------------------------------

def kalshi_events(series: str) -> list:
    out, cur = [], ""
    while True:
        d = get(f"{KX}/events?series_ticker={series}&status=open&limit=200&with_nested_markets=true"
                + (f"&cursor={cur}" if cur else ""))
        out += d.get("events", [])
        cur = d.get("cursor")
        if not cur or not d.get("events"):
            return out


def kx_day(ev_ticker: str) -> date:
    part = ev_ticker.split("-")[1]
    return date(2000 + int(part[:2]), MONTHS[part[2:5]], int(part[5:7]))


def kalshi_url(event_ticker: str) -> str:
    series = event_ticker.split("-")[0]
    return f"https://kalshi.com/markets/{series.lower()}/{KX_WEB[series]}/{event_ticker.lower()}"


def _ba(m):
    b, a = _num(m.get("yes_bid_dollars")), _num(m.get("yes_ask_dollars"))
    if b is None or a is None or not (0 < a < 1) or a - b > MAX_SPREAD:
        return None
    return b, a


def kalshi(by_key: dict, links: dict) -> dict:
    """{gid: {"ml": {...}, "spread": {...}, "total": {...}}} raw Kalshi quotes (bid/ask per rung)."""
    out = {}
    suffix_gid = {}
    for ev in kalshi_events("KXNBAGAME"):
        mk = ev.get("markets", [])
        teams = [KX_CODE.get(m["ticker"].split("-")[-1]) for m in mk]
        if len(mk) != 2 or None in teams:
            continue
        g = by_key.get((kx_day(ev["event_ticker"]), frozenset(teams)))
        if g is None:
            continue
        suffix = ev["event_ticker"].split("-", 1)[1]
        suffix_gid[suffix] = g["gid"]
        links.setdefault(g["gid"], {}).setdefault("kalshi", {})["ml"] = kalshi_url(ev["event_ticker"])
        q = {}
        for m, t in zip(mk, teams):
            ba = _ba(m)
            if ba:
                q["home" if t == g["home"] else "away"] = ba
        if len(q) == 2:
            out.setdefault(g["gid"], {})["ml"] = q
    for series, kind in (("KXNBASPREAD", "spread"), ("KXNBATOTAL", "total")):
        try:
            evs = kalshi_events(series)
        except Exception as exc:  # noqa: BLE001
            print(f"  Kalshi {kind} unavailable ({exc})")
            continue
        for ev in evs:
            gid = suffix_gid.get(ev["event_ticker"].split("-", 1)[1])
            if not gid:
                continue
            links.setdefault(gid, {}).setdefault("kalshi", {})[kind] = kalshi_url(ev["event_ticker"])
            rungs = {}
            for m in ev.get("markets", []):
                strike, ba = _num(m.get("floor_strike")), _ba(m)
                if strike is None or not ba:
                    continue
                if kind == "spread":
                    code = "".join(ch for ch in m["ticker"].split("-")[-1] if ch.isalpha())
                    tid = KX_CODE.get(code)
                    if tid is None:
                        continue
                    rungs[(tid, strike)] = ba
                else:
                    rungs[strike] = ba
            out.setdefault(gid, {})[kind] = rungs
    return out


# ----------------------------------------------------------------------
# Polymarket
# ----------------------------------------------------------------------

def poly(by_key: dict, links: dict) -> dict:
    """{gid: {"ml": (home bid, home ask), "spread": {(team, line): (bid, ask)}, "total": {line: (over bid, ask)}}}"""
    out = {}
    off = 0
    evs = []
    while True:
        d = get(f"{GAMMA}/events?series_id={POLY_SERIES}&closed=false&limit=100&offset={off}")
        evs += d
        off += 100
        if len(d) < 100:
            break
    for ev in evs:
        ms = ev.get("markets", [])
        ml = next((m for m in ms if m.get("sportsMarketType") == "moneyline"), None)
        if not ml or not ml.get("gameStartTime"):
            continue
        try:
            outs = json.loads(ml["outcomes"])
        except (TypeError, ValueError):
            continue
        teams = [NICK.get(o) for o in outs]
        if None in teams or len(teams) != 2:
            continue
        start = datetime.fromisoformat(ml["gameStartTime"].replace(" ", "T").replace("+00", "+00:00"))
        g = by_key.get((G.us_date(start.isoformat()), frozenset(teams)))
        if g is None:
            continue
        if ev.get("slug"):
            links.setdefault(g["gid"], {})["polymarket"] = f"https://polymarket.com/event/{ev['slug']}"
        q = {}
        bid, ask = _num(ml.get("bestBid")), _num(ml.get("bestAsk"))
        if bid and ask and 0 < bid < ask < 1 and ask - bid <= MAX_SPREAD:
            first_home = teams[0] == g["home"]
            q["ml"] = (bid, ask) if first_home else (1 - ask, 1 - bid)      # as (home bid, home ask)
        sp, tt = {}, {}
        for m in ms:
            kind = m.get("sportsMarketType")
            bid, ask, line = _num(m.get("bestBid")), _num(m.get("bestAsk")), _num(m.get("line"))
            if line is None or not bid or not ask or not (0 < bid < ask < 1) or ask - bid > MAX_SPREAD:
                continue
            try:
                o = json.loads(m["outcomes"])
            except (TypeError, ValueError, KeyError):
                continue
            if kind == "spreads" and o and NICK.get(o[0]) in (g["home"], g["away"]):
                sp[(NICK[o[0]], line)] = (bid, ask)          # first outcome at `line` (e.g. -5.5)
            elif kind == "totals" and o and o[0].lower() == "over":
                tt[line] = (bid, ask)
        if sp:
            q["spread"] = sp
        if tt:
            q["total"] = tt
        if q:
            out[g["gid"]] = q
    return out


# ----------------------------------------------------------------------
# Combine into the site's "shop" per game
# ----------------------------------------------------------------------

def _mid(ba):
    return (ba[0] + ba[1]) / 2


def shop(games: list, links: dict | None = None, now: datetime | None = None) -> dict:
    links = {} if links is None else links
    now = now or datetime.now(timezone.utc)
    up = [g for g in games if g["hs"] is None and g["state"] == "pre"
          and datetime.fromisoformat(g["iso"].replace("Z", "+00:00")) > now]
    by_key = {(g["day"], frozenset((g["home"], g["away"]))): g for g in up}
    try:
        kx = kalshi(by_key, links)
    except Exception as exc:  # noqa: BLE001
        print(f"  Kalshi prices unavailable ({exc})")
        kx = {}
    try:
        pm = poly(by_key, links)
    except Exception as exc:  # noqa: BLE001
        print(f"  Polymarket prices unavailable ({exc})")
        pm = {}
    out = {}
    for g in up:
        L, k, p = g["line"], kx.get(g["gid"], {}), pm.get(g["gid"], {})
        if not (L or k or p):
            continue
        h, a = g["home"], g["away"]
        fair, offers = {}, {"ml": {}, "spread": {}, "total": {}}
        books = 1 if L.get("pml") is not None or "sp" in L else 0

        # moneyline
        cands = []
        if "pml" in L:
            cands.append(L["pml"])
        if "ml" in k:
            hb, ha = k["ml"]["home"]
            ab, aa = k["ml"]["away"]
            cands.append(((hb + ha) / 2) / (((hb + ha) / 2) + ((ab + aa) / 2)))
            offers["ml"]["home"] = [offer("kalshi", min(ha, 1 - ab))]
            offers["ml"]["away"] = [offer("kalshi", min(aa, 1 - hb))]
        if "ml" in p:
            b, s = p["ml"]
            cands.append(_mid((b, s)))
            offers["ml"].setdefault("home", []).append(offer("polymarket", s))
            offers["ml"].setdefault("away", []).append(offer("polymarket", round(1 - b, 4)))
        if cands:
            fair["home"] = round(statistics.median(cands), 4)

        # spread at the sportsbook's line (home point, negative = home favored)
        if "sp" in L and L.get("hso") and L.get("aso"):
            line = L["sp"]
            fav, pts = (h, -line) if line < 0 else (a, line)          # favorite and by how many
            cands = [G.devig(L["hso"], L["aso"])]                      # chance the HOME side covers
            kr = (k.get("spread") or {}).get((fav, abs(pts)))
            if kr and line != 0:
                fav_cover = _mid(kr)
                cands.append(fav_cover if fav == h else 1 - fav_cover)
                yes, no = kr[1], round(1 - kr[0], 4)
                fav_side, dog_side = ("home", "away") if fav == h else ("away", "home")
                offers["spread"][fav_side] = [offer("kalshi", yes, -abs(pts))]
                offers["spread"][dog_side] = [offer("kalshi", no, abs(pts))]
            pr = (p.get("spread") or {}).get((fav, -abs(pts)))
            if pr and line != 0:
                fav_cover = _mid(pr)
                cands.append(fav_cover if fav == h else 1 - fav_cover)
                fav_side, dog_side = ("home", "away") if fav == h else ("away", "home")
                offers["spread"].setdefault(fav_side, []).append(offer("polymarket", pr[1], -abs(pts)))
                offers["spread"].setdefault(dog_side, []).append(offer("polymarket", round(1 - pr[0], 4), abs(pts)))
            fair["spreadPoint"], fair["spreadHome"] = line, round(statistics.median(cands), 4)

        # total at the sportsbook's line
        if "tot" in L and L.get("oo") and L.get("uo"):
            line = L["tot"]
            cands = [G.devig(L["oo"], L["uo"])]
            for venue, src in (("kalshi", (k.get("total") or {}).get(line)), ("polymarket", (p.get("total") or {}).get(line))):
                if src:
                    cands.append(_mid(src))
                    offers["total"].setdefault("over", []).append(offer(venue, src[1], line))
                    offers["total"].setdefault("under", []).append(offer(venue, round(1 - src[0], 4), line))
            fair["totalPoint"], fair["over"] = line, round(statistics.median(cands), 4)

        s = {"books": books, "venues": sum(1 for x in (k, p) if x), "fair": fair, "ml": {}, "spread": {}, "total": {}}
        for mk, sides in offers.items():
            for side, lst in sides.items():
                pf = _fair_prob(fair, mk, side, lst[0]["point"])
                for o in lst:
                    o["ev"] = None if pf is None else round((pf * o["dec"] - 1) * 100, 1)
                s[mk][side] = max(lst, key=lambda o: (o["ev"] is not None, o["ev"] or 0, o["dec"]))
        s["live"] = now.isoformat(timespec="seconds")
        out[g["gid"]] = s
    return out


def _fair_prob(fair: dict, mk: str, side: str, point) -> float | None:
    if mk == "ml" and "home" in fair:
        return fair["home"] if side == "home" else 1 - fair["home"]
    if mk == "spread" and "spreadHome" in fair:
        hp = fair["spreadPoint"]
        if side == "home" and point == hp:
            return fair["spreadHome"]
        if side == "away" and point == -hp:
            return 1 - fair["spreadHome"]
    if mk == "total" and "over" in fair and point == fair["totalPoint"]:
        return fair["over"] if side == "over" else 1 - fair["over"]
    return None


if __name__ == "__main__":
    gs = G.load()
    lk = {}
    s = shop(gs, lk)
    by = {g["gid"]: g for g in gs}
    for gid, v in sorted(s.items(), key=lambda kv: by[kv[0]]["iso"]):
        g = by[gid]
        print(g["day"], g["acode"], "at", g["hcode"], json.dumps(v["fair"]),
              {mk: {sd: (o["book"][0], o["cents"], o["point"], o["ev"]) for sd, o in v[mk].items()} for mk in ("ml", "spread", "total")})
    print(len(s), "games priced;", sum(1 for x in lk.values() if "kalshi" in x), "with Kalshi links,",
          sum(1 for x in lk.values() if "polymarket" in x), "with Polymarket links")
