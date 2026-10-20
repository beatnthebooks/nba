"""
nba/board.py
============
Build the NBA edition of Beatn' the Books (nba/site/): every game of the current season, day by day.

  * our model: walk-forward Elo with home court, back-to-backs and rest (model.py)
  * the market: consensus closing lines for finished games; DraftKings' current line for upcoming ones
  * Kalshi and Polymarket prices (markets.py), with the middle of DraftKings / Kalshi / Polymarket as "fair"
  * "Bets to take" per game, logged the first time they're shown and graded at that price (the NFL site's
    picks.py, pointed at data/nba/pick_log.json)
  * results, season record, power ratings, injuries (ESPN)

    py nba/board.py            # refresh the last 3 days + next 7 from ESPN, then rebuild
    py nba/board.py --offline  # rebuild from the files already downloaded

Writes nba/site/data.js and build/nba-artifact-index.html (the home page without its document wrapper, for claude.ai).
Standard library only.
"""

from __future__ import annotations

import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import NormalDist

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import espn  # noqa: E402
import games as G  # noqa: E402
import markets  # noqa: E402
import model as M  # noqa: E402
import signals as S  # noqa: E402

sys.path.append(str(ROOT))
import picks as P  # noqa: E402  (the NFL site's pick log, grading and scoreboard)
from edge_lab import _inverse, _solve, logit, sigmoid  # noqa: E402

P.LOG = ROOT / "data" / "nba" / "pick_log.json"
SITE = HERE / "site"
ARTIFACT_INDEX = ROOT / "build" / "nba-artifact-index.html"
ND = NormalDist()

MODEL_MIN_EDGE = 5.0          # same rule as the NFL site: suggest model picks at a model edge of 5%+
GAP_EV = 2.0                  # price gap: an exchange price at least this % better than fair, after fees
LEAN_FIT_FROM = 2020          # the model's first unseen season (tuned on 2009-10..2018-19)


def name(tid):
    return espn.TEAMS[tid][2]


def full(tid):
    return f"{espn.TEAMS[tid][1]} {espn.TEAMS[tid][2]}"


def ko_label(ko: datetime) -> str:
    return f"{ko:%a} {ko:%b} {ko.day} · {ko.strftime('%I:%M').lstrip('0')} {ko:%p} CT"


def settle(won, dec: float) -> float:
    return 0.0 if won is None else (dec - 1.0 if won else -1.0)


def real_edge(p_fair: float, shift: float, dec: float) -> float:
    return round((sigmoid(logit(p_fair) + shift) * dec - 1) * 100, 1)


def model_margin(p: float) -> float:
    """Model win chance -> expected home margin in points."""
    return 400 * math.log10(p / (1 - p)) / M.ELO_PER_PT


def spread_cover(p: float, margin_line: float, sigma: float, w: float) -> float:
    """Blend chance the HOME side covers. margin_line = the market's expected home margin (= -home spread)."""
    bm = w * model_margin(p) + (1 - w) * margin_line
    return ND.cdf((bm - margin_line) / sigma)


def real_line(L):
    return L and L.get("src") != "dk"


def _fit_offset_logit(X, offset, y, iters=40):
    """Logistic regression with the market's log-odds as a fixed offset (same as weekly.py). No data: zero shift."""
    if not y:
        return [0.0], [0.0]
    k = len(X[0])
    beta = [0.0] * k
    H = None
    for _ in range(iters):
        grad, H = [0.0] * k, [[0.0] * k for _ in range(k)]
        for x, o, t in zip(X, offset, y):
            p = sigmoid(o + sum(b * v for b, v in zip(beta, x)))
            wt = p * (1 - p)
            for i in range(k):
                grad[i] += (t - p) * x[i]
                for j in range(k):
                    H[i][j] += wt * x[i] * x[j]
        step = _solve(H, grad)
        beta = [b + s for b, s in zip(beta, step)]
        if max(abs(s) for s in step) < 1e-10:
            break
    cov = _inverse(H)
    return beta, [math.sqrt(max(cov[i][i], 0.0)) for i in range(k)]


# ----------------------------------------------------------------------
# What the model's picks have really done (walk-forward, closing prices)
# ----------------------------------------------------------------------

def _model_bets(recs, w, sigma, start, season):
    for r in recs:
        g, L = r["g"], r["g"]["line"]
        if not (start <= g["season"] < season) or g["hs"] is None or not real_line(L):
            continue
        if "pml" in L:
            f = L["pml"]
            bl = w * r["p"] + (1 - w) * f
            dh, da = G.am_to_dec(L["hml"]), G.am_to_dec(L["aml"])
            evh, eva = bl * dh - 1, (1 - bl) * da - 1
            home = evh >= eva
            yield "ml", max(evh, eva), (f if home else 1 - f), (dh if home else da), (g["hs"] > g["as"]) == home
        if "sp" in L:
            ml = -L["sp"]
            pc = spread_cover(r["p"], ml, sigma, w)
            pm = G.devig(L["hso"], L["aso"])
            dh, da = G.am_to_dec(L["hso"]), G.am_to_dec(L["aso"])
            evh, eva = pc * dh - 1, (1 - pc) * da - 1
            home = evh >= eva
            margin = g["hs"] - g["as"]
            won = None if margin == ml else (margin > ml) == home
            yield "spread", max(evh, eva), (pm if home else 1 - pm), (dh if home else da), won


def fit_shift(recs, w, sigma, season, kind):
    off, y = [], []
    for k, ev, pm, _, won in _model_bets(recs, w, sigma, LEAN_FIT_FROM, season):
        if k == kind and ev > 0 and won is not None:
            off.append(logit(pm))
            y.append(1.0 if won else 0.0)
    # With the blend at ~1% model the lean almost never beats the price, so there may be too few bets to fit:
    # then no shift (the market's own price is the realistic chance).
    beta, se = _fit_offset_logit([[1.0]] * len(y), off, y) if len(y) >= 30 else ([0.0], [0.0])
    return {"shift": round(beta[0], 5), "se": round(se[0], 5), "n": len(y), "won": int(sum(y)),
            "seasons": f"{LEAN_FIT_FROM - 1}-{season - 1}"}


def model_record(recs, w, sigma, season):
    out = {}
    for kind in ("ml", "spread"):
        rets = [0.0 if won is None else (dec - 1 if won else -1.0)
                for k, ev, _, dec, won in _model_bets(recs, w, sigma, LEAN_FIT_FROM, season)
                if k == kind and ev * 100 >= MODEL_MIN_EDGE]
        out[kind] = {"n": len(rets), "roi": round(sum(rets) / len(rets) * 100, 1) if rets else None,
                     "seasons": f"{LEAN_FIT_FROM - 1}–{str(season - 1)[2:]}"}
    return out


# ----------------------------------------------------------------------
# One game
# ----------------------------------------------------------------------

def game_row(r, w, shop, now_ct, shifts, week_of):
    g, L = r["g"], r["g"]["line"]
    p = r["p"]
    ko = G.central(g["iso"])
    final = g["hs"] is not None
    status = "final" if final else ("live" if (ko <= now_ct or g["state"] == "in") else "upcoming")
    row = {
        "id": g["gid"], "day": ko.date().isoformat(), "date": ko.date().isoformat(), "wk": week_of(ko.date()),
        "type": "POST" if g["stype"] == 3 else "PLAYIN" if g["stype"] == 5 else "REG",
        "ko": ko_label(ko), "koIso": ko.isoformat(timespec="minutes"), "status": status,
        "away": g["acode"], "home": g["hcode"], "awayName": name(g["away"]), "homeName": name(g["home"]),
        "neutral": g["neutral"], "venue": g["venue"], "city": g["city"], "notes": list(g["notes"]),
        "as": g["as"], "hs": g["hs"], "ot": g["ot"],
        "pElo": round(p, 4), "eloLine": round(r["d"] / M.ELO_PER_PT, 1),
        "rest": {"home": g["hrest"], "away": g["arest"], "hb2b": g["hb2b"], "ab2b": g["ab2b"]},
    }
    for side, b2b, tid in (("home", g["hb2b"], g["home"]), ("away", g["ab2b"], g["away"])):
        if b2b:
            row["notes"].append(f"{name(tid)} are on the second night of a back-to-back")
    if not g["hb2b"] and not g["ab2b"] and abs(g["hrest"] - g["arest"]) >= 2 and min(g["hrest"], g["arest"]) < 7:
        more = g["home"] if g["hrest"] > g["arest"] else g["away"]
        row["notes"].append(f"{name(more)} have {abs(g['hrest'] - g['arest'])} more days of rest")
    if g["neutral"] and g["city"]:
        row["notes"].append(f"Neutral court: {g['venue']}, {g['city']}")

    home_won = None
    if final:
        home_won = g["hs"] > g["as"]
        row["eloRight"] = (p >= 0.5) == home_won

    s = shop.get(g["gid"]) if not final else None
    if s:
        row["shop"] = s
        row["gaps"] = [dict(o, mk=mk, side=side) for mk in ("ml", "spread", "total")
                       for side, o in s[mk].items() if o.get("ev") is not None and o["ev"] >= GAP_EV]
    fair = (s or {}).get("fair", {}).get("home")
    src = "exchanges" if fair is not None else "books"
    if fair is None and "pml" in L:
        fair = L["pml"]
    mine = (s or {}).get("ml", {})
    if "home" in mine and "away" in mine:
        dh, da = mine["home"]["dec"], mine["away"]["dec"]
    elif L.get("hml") and L.get("aml"):
        dh, da = G.am_to_dec(L["hml"]), G.am_to_dec(L["aml"])
    else:
        dh = da = None
    m = None
    if fair is not None:
        bl = w * p + (1 - w) * fair
        m = {"fair": round(fair, 4), "blend": round(bl, 4), "lean": None, "src": src}
        if L.get("hml") and L.get("aml"):
            m["hml"], m["aml"] = int(L["hml"]), int(L["aml"])
        if dh:
            evh, eva = bl * dh - 1, (1 - bl) * da - 1
            if max(evh, eva) > 0:
                side = "home" if evh >= eva else "away"
                dec = dh if side == "home" else da
                m.update(lean=side, leanEv=round(max(evh, eva) * 100, 1), leanDec=round(dec, 4),
                         leanEdge=real_edge(fair if side == "home" else 1 - fair, shifts["lean"]["shift"], dec))
                if side in mine:
                    m["leanBook"], m["leanCents"] = mine[side]["book"], mine[side]["cents"]
                else:
                    m["leanOdds"] = int(L["hml"] if side == "home" else L["aml"])
                if final:
                    m["leanUnits"] = round(settle(home_won if side == "home" else not home_won, dec), 3)
        if final:
            m["mktRight"] = (fair >= 0.5) == home_won
        row["mkt"] = m

    # closing fair prices for the bet tracker ("vs close") once the game starts; NFL convention: spreadLine = expected
    # home margin (+ = home favored)
    if real_line(L) or final:
        cf = {}
        if "pml" in L:
            cf["home"] = round(L["pml"], 4)
        if "sp" in L:
            cf["spreadLine"] = -L["sp"]
            if L.get("hso") and L.get("aso"):
                cf["spreadHome"] = round(G.devig(L["hso"], L["aso"]), 4)
        if "tot" in L:
            cf["total"] = L["tot"]
            if L.get("oo") and L.get("uo"):
                cf["over"] = round(G.devig(L["oo"], L["uo"]), 4)
        if cf:
            row["closeFair"] = cf
    if "sp" in L:
        row["spread"] = {"line": -L["sp"], "ho": L.get("hso"), "ao": L.get("aso")}
    if "tot" in L:
        row["total"] = {"line": L["tot"], "oo": L.get("oo"), "uo": L.get("uo")}
    nb = L.get("books", 0)
    row["lineSrc"] = "DraftKings" if L.get("src") == "dk" else (f"{nb} sportsbook{'' if nb == 1 else 's'}" if L else None)
    if g["open"].get("sp") is not None:
        row["openSpread"] = -g["open"]["sp"]
    if g["open"].get("tot") is not None:
        row["openTotal"] = g["open"]["tot"]

    # model spread pick at the sportsbook line, priced where you'd bet
    if "sp" in L and L.get("hso") and L.get("aso"):
        ML = -L["sp"]
        f = (s or {}).get("fair", {})
        pm = f["spreadHome"] if f.get("spreadPoint") == L["sp"] and "spreadHome" in f else G.devig(L["hso"], L["aso"])
        offers = (s or {}).get("spread", {})
        opts = {}
        for side, pt, am in (("home", L["sp"], L["hso"]), ("away", -L["sp"], L["aso"])):
            o = offers.get(side)
            if o and o.get("point") == pt:
                opts[side] = (o["dec"], {"cents": o["cents"], "book": o["book"]})
            else:
                opts[side] = (G.am_to_dec(am), {"odds": int(am)})
        pc = spread_cover(p, ML, shifts["sigma"], w)
        evs = {"home": pc * opts["home"][0] - 1, "away": (1 - pc) * opts["away"][0] - 1}
        side = max(evs, key=evs.get)
        dec, price = opts[side]
        sl = {"side": side, "point": L["sp"] if side == "home" else -L["sp"], "ev": round(evs[side] * 100, 1),
              "dec": round(dec, 4), "edge": real_edge(pm if side == "home" else 1 - pm, shifts["spread"]["shift"], dec),
              **price}
        if final:
            margin = g["hs"] - g["as"]
            sl["units"] = round(settle(None if margin == ML else (margin > ML) == (side == "home"), dec), 3)
        row["spreadLean"] = sl
    row["picks"] = P.game_picks(row, MODEL_MIN_EDGE)
    return row


# ----------------------------------------------------------------------
# Season pieces
# ----------------------------------------------------------------------

def season_summary(rows):
    fin = [x for x in rows if x["status"] == "final"]
    with_mkt = [x for x in fin if "mkt" in x and "mktRight" in x["mkt"]]
    out = {"final": len(fin), "withLines": len(with_mkt)}
    if with_mkt:
        ys = [1.0 if x["hs"] > x["as"] else 0.0 for x in with_mkt]
        out["eloAcc"] = sum(x["eloRight"] for x in with_mkt) / len(with_mkt)
        out["mktAcc"] = sum(x["mkt"]["mktRight"] for x in with_mkt) / len(with_mkt)
        out["eloLL"] = M.log_loss([x["pElo"] for x in with_mkt], ys)
        out["mktLL"] = M.log_loss([x["mkt"]["fair"] for x in with_mkt], ys)
    leans = [x["mkt"]["leanUnits"] for x in fin if "mkt" in x and x["mkt"] and "leanUnits" in x["mkt"]]
    out["lean"] = {"n": len(leans), "units": round(sum(leans), 2), "won": sum(1 for u in leans if u > 0),
                   "lost": sum(1 for u in leans if u < 0)}
    sl = [x["spreadLean"]["units"] for x in fin if "units" in x.get("spreadLean", {})]
    out["spread"] = {"n": len(sl), "units": round(sum(sl), 2), "won": sum(1 for u in sl if u > 0),
                     "lost": sum(1 for u in sl if u < 0)}
    by = []
    for wk in sorted({x["wk"] for x in rows}):
        f = [x for x in fin if x["wk"] == wk]
        if not f:
            continue
        lu = [x["mkt"]["leanUnits"] for x in f if "mkt" in x and x["mkt"] and "leanUnits" in x["mkt"]]
        su = [x["spreadLean"]["units"] for x in f if "units" in x.get("spreadLean", {})]
        days = sorted(x["day"] for x in f)
        by.append({"wk": wk, "from": days[0], "to": days[-1], "games": len(f),
                   "eloRight": sum(1 for x in f if x.get("eloRight")),
                   "mktRight": sum(1 for x in f if (x.get("mkt") or {}).get("mktRight")),
                   "decided": sum(1 for x in f if "eloRight" in x),
                   "leanN": len(lu), "leanUnits": round(sum(lu), 2), "spreadN": len(su), "spreadUnits": round(sum(su), 2)})
    out["byWeek"] = by
    return out


def season_models(recs, season, w):
    rows = M.collect(recs, {season})
    if not rows:
        return []
    out = []
    ys = [y for _, _, y, _ in rows]
    acc = lambda q: sum((a >= 0.5) == (y == 1) for a, y in zip(q, ys)) / len(ys)  # noqa: E731
    for label, kind, bl in (("Our model (Elo + home court + rest)", "site", None),
                            (f"Blend, {round(w * 100)}% model (its picks)", "site", w)):
        rr = M.collect(recs, {season}, bl)
        n0, r0, _ = M.roi(rr, 0.0)
        n3, r3, _ = M.roi(rr, 0.03)
        ps = [p for p, *_ in rr]
        out.append({"label": label, "kind": kind, "n": len(rr), "ll": round(M.log_loss(ps, ys), 4), "acc": round(acc(ps), 4),
                    "roi": round((r0 or 0) * 100, 1), "bets": n0, "roi3": round((r3 or 0) * 100, 1), "bets3": n3})
    ms = [m for _, m, _, _ in rows]
    out.append({"label": "Closing market", "kind": "market", "n": len(rows), "ll": round(M.log_loss(ms, ys), 4),
                "acc": round(acc(ms), 4)})
    return out


def team_table(recs, ratings, season, rows, now_ct):
    rec = defaultdict(lambda: [0, 0])
    for x in rows:
        if x["status"] == "final" and x["type"] == "REG":
            rec[x["home"]][0 if x["hs"] > x["as"] else 1] += 1
            rec[x["away"]][0 if x["as"] > x["hs"] else 1] += 1
    week_ago = (now_ct - timedelta(days=7)).isoformat()
    before = {}
    hist = defaultdict(list)
    for r in recs:
        g = r["g"]
        if g["season"] < season - 1 or g["hs"] is None:
            continue
        day = g["day"].isoformat()
        hist[g["home"]].append([day, round(r["rh"], 1), g["acode"], g["season"]])
        hist[g["away"]].append([day, round(r["ra"], 1), g["hcode"], g["season"]])
    for tid in espn.TEAMS:
        h = [x for x in hist[tid] if x[0] < week_ago and x[3] == season]
        before[tid] = h[-1][1] if h else None
    out = []
    today = now_ct.date().isoformat()
    for tid, v in sorted(((t, ratings.get(t, M.MEAN)) for t in espn.TEAMS), key=lambda kv: -kv[1]):
        code = espn.CODE[tid]
        w_, l_ = rec[code]
        prev = before[tid]
        # a team that hasn't played this season yet carries last season's rating after the summer regression
        out.append({"team": code, "name": name(tid), "full": full(tid), "rating": round(v, 1),
                    "delta": round(v - prev, 1) if prev is not None else None, "record": f"{w_}-{l_}",
                    "color": "#" + espn.TEAMS[tid][3], "hist": hist[tid] + [[today, round(v, 1), None, season]]})
    return out


def week_index(season_start):
    """Week number of the season: week 1 = opening night through the first Sunday."""
    first_monday = season_start - timedelta(days=season_start.weekday())
    return lambda d: (d - first_monday).days // 7 + 1


DERIVED = ROOT / "results" / "nba_derived.json"


def derived(games, recs, w, season, recompute=False) -> dict:
    """Numbers that need the betting-line history (data/nba/odds.json, PC only): the margin spread around the line
    (sigma, 2013-14..2018-19) and what the model's leans and picks really returned from its first unseen season to
    last season. Saved to results/nba_derived.json, which the public GitHub build reads instead (GitHub only has the
    current season's lines). They only change once a season: rerun `py nba/board.py --derive` on the PC each new season."""
    saved = json.loads(DERIVED.read_text(encoding="utf-8")) if DERIVED.exists() else None
    has_history = any(g["season"] in S.DEV and "pml" in g["line"] for g in games)
    if saved and (not recompute and saved.get("season") == season or not has_history):
        return saved
    if not has_history:
        raise RuntimeError("no betting-line history: run on the PC with data/nba/odds.json, "
                           "or keep results/nba_derived.json in the repo")
    sigma = S.fit_sigma(games, S.DEV)
    out = {"season": season, "made": datetime.now(timezone.utc).isoformat(timespec="minutes"),
           "shifts": {"lean": fit_shift(recs, w, sigma, season, "ml"), "spread": fit_shift(recs, w, sigma, season, "spread"),
                      "sigma": sigma},
           "record": model_record(recs, w, sigma, season)}
    DERIVED.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


def build(now_utc: datetime | None = None, offline=False) -> dict:
    now_utc = now_utc or datetime.now(timezone.utc)
    now_ct = G.central(now_utc.isoformat())
    games = G.load()
    params, w = M.load_settings()
    recs, ratings = M.run(games, **params)
    season = max(g["season"] for g in games)
    # ratings as of now, with the off-season regression applied to teams that haven't played yet this season
    played = {t for g in games if g["season"] == season and g["hs"] is not None for t in (g["home"], g["away"])}
    for t in espn.TEAMS:
        if t not in played:
            ratings[t] = M.MEAN + params["carry"] * (ratings.get(t, M.MEAN) - M.MEAN)
    dv = derived(games, recs, w, season)
    shifts, record = dv["shifts"], dv["record"]
    links = {}
    shop = {} if offline else markets.shop(games, links, now_utc)
    this = [r for r in recs if r["g"]["season"] == season]
    start = min(G.central(r["g"]["iso"]).date() for r in this)
    week_of = week_index(start)
    rows = [game_row(r, w, shop, now_ct, shifts, week_of) for r in this]
    for x in rows:
        if x["status"] == "upcoming" and x["id"] in links:
            x["links"] = links[x["id"]]
    by_gid = {g["gid"]: g for g in games}
    adapt = {}
    for gid, g in by_gid.items():                     # picks.grade() reads nflverse-style fields
        if g["season"] != season:
            continue
        L = g["line"]
        adapt[gid] = {"hs": g["hs"], "as": g["as"], "hml": L.get("hml"), "aml": L.get("aml"),
                      "spread": -L["sp"] if "sp" in L else None, "hso": L.get("hso"), "aso": L.get("aso"),
                      "tot": L.get("tot"), "oo": L.get("oo"), "uo": L.get("uo")}
    log = P.update_log(rows, now_ct.isoformat(timespec="minutes"))
    P.apply_log(rows, adapt, log)
    try:
        inj = espn.injuries() if not offline else {}
    except Exception as exc:  # noqa: BLE001
        inj = None
        print(f"  injury feed unavailable ({exc})")
    if inj:
        order = {"Out": 0, "Doubtful": 1, "Questionable": 2, "Day-To-Day": 3}
        for x in rows:
            if x["status"] == "final":
                continue
            x["injuries"] = {}
            for side in ("away", "home"):
                lst = sorted(inj.get(espn.ID_BY_CODE[x[side]], []), key=lambda p: order.get(p["status"], 9))
                x["injuries"][side] = [{"name": p["name"], "pos": p["pos"], "status": p["status"],
                                        "comment": p["comment"][:160]} for p in lst if p["status"] in order][:8]
    today = now_ct.date().isoformat()
    days = sorted({x["day"] for x in rows})
    open_days = [d for d in days if d >= today and any(x["day"] == d and x["status"] != "final" for x in rows)]
    current = today if today in days else (open_days[0] if open_days else days[-1])
    teams = team_table(recs, ratings, season, rows, now_ct)
    return {
        "sport": "nba", "season": season, "seasonLabel": f"{season - 1}–{str(season)[2:]}",
        "updated": now_ct.isoformat(timespec="minutes"),
        "updatedLabel": f"{now_ct:%a} {now_ct:%b} {now_ct.day}, {now_ct.strftime('%I:%M').lstrip('0')} {now_ct:%p} CT",
        "today": today, "currentDay": current, "currentWeek": week_of(datetime.fromisoformat(current).date()),
        "blendW": w, "hfaPts": round(recs[-1]["hfa"] / M.ELO_PER_PT, 1) if recs else None, "params": params,
        "modelMinEdge": MODEL_MIN_EDGE, "modelRecord": record, "unitPct": P.UNIT_PCT, "fees": markets.FEE,
        "gapEv": GAP_EV, "pickShifts": shifts, "exchangeGames": len(shop), "injuriesOk": bool(inj),
        "games": rows,
        "summary": dict(season_summary(rows), picks=P.scoreboard(rows),
                        pickLogStarted=log.get("_meta", {}).get("started"), models=season_models(recs, season, w)),
        "teams": teams,
    }


def _between(text, a, b):
    i, j = text.find(a), text.find(b)
    if i < 0 or j < 0:
        sys.exit(f"Couldn't find {a} ... {b} in nba/site/index.html")
    return text[i + len(a):j]


def bust_cache(stamp: str) -> None:
    """GitHub Pages lets browsers reuse files for 10 minutes, so on GitHub (only) tag asset links in nba/site/*.html
    with a version: a content hash for code and the tab icon, the build stamp for data.js (same as weekly.bust_cache)."""
    import hashlib
    import re
    h = lambda *p: hashlib.sha1(SITE.joinpath(*p).read_bytes()).hexdigest()[:8]  # noqa: E731
    ver = {"assets/app.js": h("assets", "app.js"), "assets/style.css": h("assets", "style.css"),
           "tab-icon.svg": h("tab-icon.svg"), "data.js": re.sub(r"\D", "", stamp)}
    pat = re.compile(r'(assets/app\.js|assets/style\.css|tab-icon\.svg|data\.js)(\?v=[^"]*)?"')
    for page in SITE.glob("*.html"):
        text = page.read_text(encoding="utf-8")
        new = pat.sub(lambda m: f'{m.group(1)}?v={ver[m.group(1)]}"', text)
        if new != text:
            page.write_text(new, encoding="utf-8")


def write_site(data: dict) -> Path:
    blob = json.dumps(data, separators=(",", ":"), default=str).replace("</", "<\\/")
    (SITE / "data.js").write_text(f"window.EDGE={blob};\n", encoding="utf-8")
    if os.environ.get("GITHUB_ACTIONS") == "true":     # public site only; claude.ai pushes new versions itself
        bust_cache(data["updated"])
    index = (SITE / "index.html").read_text(encoding="utf-8")
    ARTIFACT_INDEX.parent.mkdir(exist_ok=True)
    ARTIFACT_INDEX.write_text(_between(index, "<!--head-->", "<!--/head-->").strip() + "\n"
                              + _between(index, "<!--body-->", "<!--/body-->").strip() + "\n", encoding="utf-8")
    return SITE / "data.js"


def main():
    offline = "--offline" in sys.argv
    if "--derive" in sys.argv:                 # PC, once a season: refresh results/nba_derived.json + history_scores.csv
        games = G.load()
        params, w = M.load_settings()
        recs, _ = M.run(games, **params)
        season = max(g["season"] for g in games)
        derived(games, recs, w, season, recompute=True)
        n = G.export_scores(season)
        print(f"Wrote {DERIVED.relative_to(ROOT)} and {G.HISTORY.relative_to(ROOT)} ({n} games before {season - 1}-{str(season)[2:]})")
        return
    if not offline:
        import download
        # every missing day of the current season (GitHub's first run, or after the PC was off) + the last 3 and next 7
        ev = download.fetch_scores(log=lambda *_: None)
        download.fetch_odds(ev, log=lambda *_: None)
    data = build(offline=offline)
    out = write_site(data)
    day = [x for x in data["games"] if x["day"] == data["currentDay"]]
    s = data["summary"]
    print(f"Wrote {out.relative_to(ROOT)}: {data['seasonLabel']} · {data['currentDay']} ({len(day)} games, "
          f"{sum(1 for x in day if x.get('mkt'))} with lines, {data['exchangeGames']} games with Kalshi/Polymarket prices). "
          f"Season: {s['final']} final; picks {s['picks']['all']['won']}-{s['picks']['all']['lost']}.")


if __name__ == "__main__":
    main()
