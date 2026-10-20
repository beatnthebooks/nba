"""
nba/model.py
============
The NBA Elo model, walk-forward: every game's number is made before that game's result is used.

    P(home wins) = 1 / (1 + 10^(-d/400)),   d = R_home + HFA + adj - R_away
    adj = b2b x (away on a back-to-back - home on a back-to-back) + rest x clip(rest difference, -3, 3)
    after the game: R += K x MOV multiplier x (result - P)          (FiveThirtyEight's NBA multiplier)
    new season: R = 1505 + carry x (R - 1505)

Home court is not a constant: it fell in the NBA (about 3.5 points before 2020, closer to 2 since), so HFA is the
league's average home margin over the last two seasons plus this one so far (regular season, home arenas only),
in Elo points (ELO_PER_PT per point), known before each game. Fixed in advance, Oct 20 2026.

Tuning: K, carry, b2b and rest are chosen by log loss on game RESULTS of 2009-10 to 2018-19 only (no betting lines
used). 2008-09 is burn-in. Everything from 2019-20 on is out-of-sample. Results: results/nba_backtest.txt.

    py nba/model.py            # tune (if --tune) and run the backtest against closing lines

Standard library only.
"""

from __future__ import annotations

import itertools
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import games as G  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "results" / "nba_model_settings.json"
OUT = ROOT / "results" / "nba_backtest.txt"

TRAIN = set(range(2010, 2020))          # 2009-10 .. 2018-19: tuning seasons (results only)
TEST = set(range(2020, 2027))           # 2019-20 .. 2025-26: scored once against the closing lines
ELO_PER_PT = 28.0                       # Elo points per point of margin (FiveThirtyEight's NBA scale)
MEAN = 1505.0
DEFAULTS = {"k": 20.0, "carry": 0.75, "b2b": 30.0, "rest": 5.0, "hfa_min_games": 300}


def win_prob(d: float) -> float:
    return 1.0 / (1.0 + 10 ** (-d / 400.0))


def mov_mult(margin: float, elo_diff_winner: float) -> float:
    return ((abs(margin) + 3) ** 0.8) / (7.5 + 0.006 * elo_diff_winner)


class HomeCourt:
    """League home margin, last two seasons + this season so far (home arenas, regular season)."""

    def __init__(self):
        self.by = defaultdict(lambda: [0.0, 0])

    def elo(self, season: int) -> float:
        s = n = 0.0
        for y in (season - 2, season - 1, season):
            s += self.by[y][0]
            n += self.by[y][1]
        if n < 300:
            return 3.0 * ELO_PER_PT
        return s / n * ELO_PER_PT

    def add(self, g):
        if not g["neutral"] and not g["playoff"]:
            b = self.by[g["season"]]
            b[0] += g["hs"] - g["as"]
            b[1] += 1


def run(games, k=20.0, carry=0.75, b2b=30.0, rest=5.0, **_):
    """Walk-forward Elo. Returns (recs, ratings): recs[i] = {"g", "p", "rh", "ra", "hfa", "adj"} before game i."""
    R = defaultdict(lambda: MEAN)
    season_of = {}
    hc = HomeCourt()
    recs = []
    for g in games:
        for t in (g["home"], g["away"]):
            if season_of.get(t) not in (None, g["season"]):
                R[t] = MEAN + carry * (R[t] - MEAN)
            season_of[t] = g["season"]
        hfa = 0.0 if g["neutral"] else hc.elo(g["season"])
        adj = b2b * (float(g["ab2b"]) - float(g["hb2b"])) + rest * max(-3, min(3, g["hrest"] - g["arest"]))
        d = R[g["home"]] + hfa + adj - R[g["away"]]
        p = win_prob(d)
        recs.append({"g": g, "p": p, "rh": R[g["home"]], "ra": R[g["away"]], "hfa": hfa, "adj": adj, "d": d})
        if g["hs"] is None:
            continue
        margin = g["hs"] - g["as"]
        y = 1.0 if margin > 0 else 0.0
        dw = d if margin > 0 else -d
        delta = k * mov_mult(margin, dw) * (y - p)
        R[g["home"]] += delta
        R[g["away"]] -= delta
        hc.add(g)
    return recs, dict(R)


# ----------------------------------------------------------------------
# Scoring
# ----------------------------------------------------------------------

def log_loss(ps, ys):
    return -sum(math.log(max(1e-12, p if y else 1 - p)) for p, y in zip(ps, ys)) / len(ps)


def train_loss(games, params, seasons=TRAIN):
    recs, _ = run(games, **params)
    ps, ys = [], []
    for r in recs:
        g = r["g"]
        if g["season"] in seasons and g["hs"] is not None:
            ps.append(r["p"])
            ys.append(1.0 if g["hs"] > g["as"] else 0.0)
    return log_loss(ps, ys)


def tune(games, log=print):
    """Coordinate search on the training seasons, then a small full grid around the best point."""
    grid = {"k": [12, 15, 18, 20, 22, 25, 28], "carry": [0.55, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9],
            "b2b": [0, 15, 25, 35, 45, 55, 65], "rest": [0, 3, 6, 10]}
    best = dict(DEFAULTS)
    best_ll = train_loss(games, best)
    for _ in range(3):
        moved = False
        for key, vals in grid.items():
            for v in vals:
                cand = dict(best, **{key: v})
                ll = train_loss(games, cand)
                if ll < best_ll - 1e-7:
                    best, best_ll, moved = cand, ll, True
        log(f"  pass: {best} log loss {best_ll:.5f}")
        if not moved:
            break
    return best, best_ll


# ----------------------------------------------------------------------
# Backtest against the closing lines
# ----------------------------------------------------------------------

def collect(recs, seasons, blend=None):
    """(model p, market fair p, outcome, (home dec, away dec)) for decided games with a closing moneyline."""
    out = []
    for r in recs:
        g = r["g"]
        L = g["line"]
        if g["season"] not in seasons or g["hs"] is None or "pml" not in L or L.get("src") == "dk":
            continue
        p = r["p"] if blend is None else blend * r["p"] + (1 - blend) * L["pml"]
        out.append((p, L["pml"], 1.0 if g["hs"] > g["as"] else 0.0, (G.am_to_dec(L["hml"]), G.am_to_dec(L["aml"]))))
    return out


def roi(rows, min_ev=0.0):
    rets = []
    for p, _, y, (dh, da) in rows:
        evh, eva = p * dh - 1, (1 - p) * da - 1
        if max(evh, eva) <= min_ev:
            continue
        rets.append((dh - 1 if y else -1.0) if evh >= eva else (da - 1 if not y else -1.0))
    if not rets:
        return 0, None, None
    mu = sum(rets) / len(rets)
    sd = math.sqrt(sum((x - mu) ** 2 for x in rets) / max(1, len(rets) - 1))
    return len(rets), mu, (mu / (sd / math.sqrt(len(rets))) if sd else 0.0)


def fit_blend(recs, seasons):
    """Blend weight w (model share) that minimises log loss of w*p_model + (1-w)*p_market on the given seasons."""
    rows = collect(recs, seasons)
    best = (None, 0.0)
    for w in [i / 100 for i in range(0, 61)]:
        ll = log_loss([w * p + (1 - w) * m for p, m, _, _ in rows], [y for *_, y, _ in rows])
        if best[0] is None or ll < best[0]:
            best = (ll, w)
    return best[1]


def report(games, params, blend_w, log=print):
    recs, ratings = run(games, **params)
    lines = []
    out = lambda s="": (lines.append(s), log(s))  # noqa: E731
    out("NBA Elo vs the closing line (ESPN consensus of sportsbooks)")
    out(f"Settings tuned on 2009-10..2018-19 results only: {json.dumps(params)}; blend weight {blend_w} "
        "(fit on 2013-14..2018-19 lines)")
    out("")
    hdr = f"{'season':<9}{'games':>6}{'model LL':>10}{'market LL':>11}{'blend LL':>10}{'model acc':>10}{'mkt acc':>9}"
    out(hdr)
    allm, allk, allb, ally = [], [], [], []
    for s in sorted({g['season'] for g in games if g['season'] >= 2014}):
        rows = collect(recs, {s})
        if not rows:
            continue
        ps = [p for p, *_ in rows]
        ms = [m for _, m, *_ in rows]
        bs = [blend_w * p + (1 - blend_w) * m for p, m, *_ in rows]
        ys = [y for _, _, y, _ in rows]
        if s in TEST:
            allm += ps; allk += ms; allb += bs; ally += ys
        acc = lambda q: sum((a >= 0.5) == (y == 1) for a, y in zip(q, ys)) / len(ys)  # noqa: E731
        tag = "  (test)" if s in TEST else ("" if s < 2027 else "  (this season)")
        out(f"{s - 1}-{str(s)[2:]:<4}{len(rows):>6}{log_loss(ps, ys):>10.4f}{log_loss(ms, ys):>11.4f}"
            f"{log_loss(bs, ys):>10.4f}{acc(ps):>10.1%}{acc(ms):>9.1%}{tag}")
    if ally:
        acc = lambda q: sum((a >= 0.5) == (y == 1) for a, y in zip(q, ally)) / len(ally)  # noqa: E731
        out(f"{'TEST all':<9}{len(ally):>6}{log_loss(allm, ally):>10.4f}{log_loss(allk, ally):>11.4f}"
            f"{log_loss(allb, ally):>10.4f}{acc(allm):>10.1%}{acc(allk):>9.1%}")
    out("")
    out("Betting every positive-EV side at the closing moneyline, TEST seasons 2019-20..2025-26:")
    for label, bl in (("model alone", None), (f"blend {blend_w}", blend_w)):
        rows = collect(recs, TEST, bl)
        for thr in (0.0, 0.03, 0.05):
            n, mu, t = roi(rows, thr)
            out(f"  {label:<12} EV > {thr:.0%}: {n:>5} bets  ROI {mu * 100 if mu is not None else 0:+6.2f}%  (t = {t or 0:+.2f})")
    rows = collect(recs, TEST)
    fav = [(m >= 0.5, y, d) for _, m, y, d in rows]
    r_f = [(dh - 1 if y else -1.0) if hf else (da - 1 if not y else -1.0) for hf, y, (dh, da) in fav]
    r_d = [(da - 1 if not y else -1.0) if hf else (dh - 1 if y else -1.0) for hf, y, (dh, da) in fav]
    r_h = [(dh - 1 if y else -1.0) for _, _, y, (dh, da) in rows]
    out(f"  blind: every favorite {sum(r_f) / len(r_f):+.2%}, every underdog {sum(r_d) / len(r_d):+.2%}, "
        f"every home team {sum(r_h) / len(r_h):+.2%} ({len(rows)} games)")
    return recs, ratings, "\n".join(lines)


def load_settings():
    try:
        s = json.loads(SETTINGS.read_text(encoding="utf-8"))
        return s["params"], s["blend_w"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return dict(DEFAULTS), 0.2


def main():
    games = G.load()
    print(f"{len(games)} games loaded")
    if "--tune" in sys.argv or not SETTINGS.exists():
        params, ll = tune(games)
        recs, _ = run(games, **params)
        blend_w = fit_blend(recs, set(range(2014, 2020)))
        SETTINGS.write_text(json.dumps({"params": params, "train_ll": round(ll, 5), "blend_w": blend_w,
                                        "train": "2010-2019", "blend_fit": "2014-2019"}, indent=1), encoding="utf-8")
    params, blend_w = load_settings()
    _, _, text = report(games, params, blend_w)
    OUT.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
