"""
nba/signals.py
==============
The NBA edge search, same protocol as the NFL's edge_lab.py: given the market's own closing price, does anything
known before tip-off still predict the result? Each candidate is tested as a market residual

    logit P(outcome) = b0 + b1 * logit(p_market) + b2 * feature

on three markets: moneyline (home wins), spread (home covers), total (over). b2 = 0 means the market prices it.

Protocol, fixed before any test-season number was looked at (Oct 20, 2026):
  * DEV seasons 2013-14 .. 2018-19 (ESPN's lines start in 2013-14). A feature is SELECTED only if |z| >= 2 on DEV
    AND b2 has the same sign in both halves (2013-14..2015-16 and 2016-17..2018-19).
  * TEST seasons 2019-20 .. 2025-26, scored ONCE: selected features combined per market, each test season predicted
    with coefficients fit on all earlier seasons only. Bets at the consensus closing price.
  * Every feature uses only information from before tip-off (walk-forward Elo, earlier games only).

    py nba/signals.py           # DEV screening only
    py nba/signals.py --test    # screening + the one-time out-of-sample test  -> results/nba_signals.txt

Standard library only.
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import NormalDist

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import games as G  # noqa: E402
import model as M  # noqa: E402

sys.path.append(str(ROOT))
from edge_lab import fit_logit, logit, sigmoid  # noqa: E402  (the NFL lab's small logistic regression)

DEV = set(range(2014, 2020))
TEST = set(range(2020, 2027))
EV_THRESHOLDS = (0.0, 0.02, 0.04)
ND = NormalDist()
OUT = ROOT / "results" / "nba_signals.txt"


class Team:
    def __init__(self):
        self.reset()

    def reset(self):
        self.n = 0
        self.pf = self.pa = 0.0
        self.ats = self.ou = 0.0
        self.last_ats = self.last_margin = self.last_ou = 0.0
        self.streak = 0
        self.last_ot = False


def fit_sigma(games, seasons):
    """Std-dev of the final margin around the spread (home line, negative = home favored), by log loss."""
    data = [(-g["line"]["sp"], 1.0 if g["hs"] > g["as"] else 0.0) for g in games
            if g["season"] in seasons and g["hs"] is not None and "sp" in g["line"] and g["line"].get("src") != "dk"]
    best = None
    for s10 in range(80, 181):
        s = s10 / 10
        ll = -sum(math.log(max(1e-12, ND.cdf(m / s) if y else 1 - ND.cdf(m / s))) for m, y in data)
        if best is None or ll < best[0]:
            best = (ll, s)
    return best[1]


def build_rows(games, recs, sigma):
    st = defaultdict(Team)
    league = {"pts": [0.0, 0], "line": [0.0, 0]}
    season = None
    rows = []
    for g, r in zip(games, recs):
        if g["season"] != season:
            season = g["season"]
            for t in st.values():
                t.reset()
            league = {"pts": [0.0, 0], "line": [0.0, 0]}
        h, a = st[g["home"]], st[g["away"]]
        L = g["line"]
        row = {"g": g, "season": g["season"], "played": g["hs"] is not None, "elo": r["p"]}
        real = L.get("src") != "dk"
        if real and "pml" in L:
            row["p_ml"] = L["pml"]
            row["ml_odds"] = (L["hml"], L["aml"])
        if real and "sp" in L:
            row["p_cover"] = G.devig(L["hso"], L["aso"])
            row["sp_odds"] = (L["hso"], L["aso"])
            row["p_sp_win"] = ND.cdf(-L["sp"] / sigma)
        if real and "tot" in L:
            row["p_over"] = G.devig(L["oo"], L["uo"])
            row["tot_odds"] = (L["oo"], L["uo"])
        if row["played"]:
            res = g["hs"] - g["as"]
            row["y_ml"] = 1.0 if res > 0 else 0.0
            if "sp" in L:
                row["y_spread"] = None if res + L["sp"] == 0 else float(res + L["sp"] > 0)
            if "tot" in L:
                tt = g["hs"] + g["as"]
                row["y_total"] = None if tt == L["tot"] else float(tt > L["tot"])

        sp = L.get("sp", 0.0) or 0.0
        base = row.get("p_ml") or row.get("p_sp_win")
        lp = league["pts"][0] / league["pts"][1] if league["pts"][1] else 105.0
        kk = 8.0
        sh = lambda t, attr: (getattr(t, attr) + kk * lp) / (t.n + kk)  # noqa: E731
        exp_h = (sh(h, "pf") + sh(a, "pa")) / 2
        exp_a = (sh(a, "pf") + sh(h, "pa")) / 2
        f = {}
        f["elo_gap"] = logit(r["p"]) - logit(base) if base else 0.0
        f["b2b"] = float(g["ab2b"]) - float(g["hb2b"])
        f["rest_diff"] = max(-3, min(3, g["hrest"] - g["arest"]))
        f["three_in_four"] = float(g["a3in4"]) - float(g["h3in4"])
        f["tz_travel"] = g["atz"] - g["htz"]
        f["altitude"] = float(g["home"] in G.ALTITUDE and g["away"] not in G.ALTITUDE and not g["neutral"])
        f["trip_len"] = min(g["atrip"], 7) - min(g["htrip"], 7)
        f["last_margin"] = max(-30, min(30, h.last_margin)) - max(-30, min(30, a.last_margin))
        f["last_ats"] = max(-25, min(25, h.last_ats)) - max(-25, min(25, a.last_ats))
        f["season_ats"] = h.ats / (h.n + 5) - a.ats / (a.n + 5)
        f["streak"] = max(-5, min(5, h.streak)) - max(-5, min(5, a.streak))
        f["home_dog"] = float(sp > 0)
        f["big_dog"] = float(sp >= 10) - float(sp <= -10)
        f["early_elo"] = f["elo_gap"] * float(g["hn"] < 10 and g["an"] < 10)
        f["playoff"] = float(g["playoff"])
        f["ml_vs_spread"] = (logit(row["p_ml"]) - logit(row["p_sp_win"])) if "p_ml" in row and "p_sp_win" in row else 0.0
        f["pts_gap"] = (exp_h - exp_a) - (-sp) if "sp" in L else 0.0
        row["side"] = f

        t = {}
        ll = league["line"][0] / league["line"][1] if league["line"][1] else (L.get("tot") or 210.0)
        t["any_b2b"] = float(g["hb2b"]) + float(g["ab2b"])
        t["rest_sum"] = min(g["hrest"], 4) + min(g["arest"], 4)
        t["altitude"] = float(g["home"] in G.ALTITUDE and not g["neutral"])
        t["line_level"] = (L["tot"] - ll) if "tot" in L else 0.0
        t["team_ou"] = (h.ou / (h.n + 5) + a.ou / (a.n + 5)) / 2
        t["last_ou"] = (max(-30, min(30, h.last_ou)) + max(-30, min(30, a.last_ou))) / 2
        t["pts_model"] = (exp_h + exp_a - L["tot"]) if "tot" in L else 0.0
        t["abs_spread"] = abs(sp)
        t["early_season"] = float(g["hn"] < 10 and g["an"] < 10)
        t["playoff"] = float(g["playoff"])
        t["tz_sum"] = g["htz"] + g["atz"]
        t["ot_last"] = float(h.last_ot) + float(a.last_ot)
        t["three_in_four"] = float(g["h3in4"]) + float(g["a3in4"])
        row["tot"] = t
        rows.append(row)

        # ---- update after the game (the next game's features see this result) ----
        if "tot" in L:
            league["line"][0] += L["tot"]
            league["line"][1] += 1
        if not row["played"]:
            continue
        res = g["hs"] - g["as"]
        league["pts"][0] += g["hs"] + g["as"]
        league["pts"][1] += 2
        for tm, pf, pa, sign in ((h, g["hs"], g["as"], 1), (a, g["as"], g["hs"], -1)):
            tm.n += 1
            tm.pf += pf
            tm.pa += pa
            tm.last_margin = pf - pa
            tm.last_ats = (pf - pa) + sign * sp if "sp" in L else 0.0
            tm.ats += tm.last_ats
            tm.last_ot = g["ot"]
            won = pf > pa
            tm.streak = (max(tm.streak, 0) + 1) if won else (min(tm.streak, 0) - 1)
            if "tot" in L:
                tm.last_ou = pf + pa - L["tot"]
                tm.ou += tm.last_ou
    return rows


MARKETS = {
    "ml": ("p_ml", "y_ml", "side", lambda r: r["ml_odds"]),
    "spread": ("p_cover", "y_spread", "side", lambda r: r["sp_odds"]),
    "total": ("p_over", "y_total", "tot", lambda r: r["tot_odds"]),
}


def market_rows(rows, market, seasons):
    pkey, ykey, _, _ = MARKETS[market]
    return [r for r in rows if r["season"] in seasons and r["played"]
            and r.get(pkey) is not None and r.get(ykey) is not None]


def design(r, market, feats):
    pkey, _, grp, _ = MARKETS[market]
    return [1.0, logit(r[pkey])] + [r[grp][f] for f in feats]


def log_loss(ps, ys):
    return -sum(y * math.log(p) + (1 - y) * math.log(1 - p) for p, y in zip(ps, ys)) / len(ps)


def screen(rows, market):
    _, ykey, grp, _ = MARKETS[market]
    dev = sorted(DEV)
    halves = (set(dev[:len(dev) // 2]), set(dev[len(dev) // 2:]))
    data = market_rows(rows, market, DEV)
    out = []
    for f in data[0][grp]:
        vals = [r[grp][f] for r in data]
        if max(vals) == min(vals):
            continue
        b, se = fit_logit([design(r, market, [f]) for r in data], [r[ykey] for r in data])
        z = b[2] / se[2] if se[2] else 0.0
        signs = []
        for hs in halves:
            d2 = [r for r in data if r["season"] in hs]
            b2, _ = fit_logit([design(r, market, [f]) for r in d2], [r[ykey] for r in d2])
            signs.append(math.copysign(1, b2[2]))
        stable = signs[0] == signs[1]
        out.append({"feat": f, "coef": b[2], "z": z, "stable": stable, "selected": abs(z) >= 2.0 and stable})
    bb, sb = fit_logit([design(r, market, []) for r in data], [r[ykey] for r in data])
    return out, (bb, sb, len(data))


def am_dec(x):
    return G.am_to_dec(x)


def test_market(rows, market, feats):
    pkey, ykey, _, odds = MARKETS[market]
    preds = []
    for s in sorted(TEST):
        train = market_rows(rows, market, set(range(min(DEV), s)))
        b, _ = fit_logit([design(r, market, feats) for r in train], [r[ykey] for r in train])
        for r in market_rows(rows, market, {s}):
            x = design(r, market, feats)
            preds.append((r, sigmoid(sum(bi * xi for bi, xi in zip(b, x)))))
    ys = [r[ykey] for r, _ in preds]
    res = {"n": len(preds), "ll_model": log_loss([p for _, p in preds], ys),
           "ll_mkt": log_loss([r[pkey] for r, _ in preds], ys), "bets": {t: [] for t in EV_THRESHOLDS}}
    for r, p in preds:
        oh, oa = odds(r)
        dh, da = am_dec(oh), am_dec(oa)
        evh, eva = p * dh - 1, (1 - p) * da - 1
        y = r[ykey]
        for thr in EV_THRESHOLDS:
            if max(evh, eva) <= thr:
                continue
            ret = (dh - 1 if y == 1 else -1.0) if evh >= eva else (da - 1 if y == 0 else -1.0)
            res["bets"][thr].append((r["season"], ret))
    return res


def summarize(bets):
    n = len(bets)
    if not n:
        return "no bets"
    rets = [x for _, x in bets]
    mean = sum(rets) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in rets) / max(1, n - 1))
    t = mean / (sd / math.sqrt(n)) if sd else 0.0
    by = defaultdict(float)
    for s, x in bets:
        by[s] += x
    pos = sum(1 for v in by.values() if v > 0)
    return f"{n:>5} bets  ROI {mean * 100:+6.2f}%  (t = {t:+.2f})  winning seasons {pos}/{len(by)}"


def blind(rows):
    out = []
    for market, sides in (("ml", ("home", "away")), ("spread", ("home", "away")), ("total", ("over", "under"))):
        data = market_rows(rows, market, TEST)
        _, ykey, _, odds = MARKETS[market]
        for i, side in enumerate(sides):
            rets = [(am_dec(odds(r)[i]) - 1 if (r[ykey] == 1) == (i == 0) else -1.0) for r in data]
            out.append(f"  every {side:<6} {market:<7} {len(rets):>5} bets  ROI {sum(rets) / len(rets) * 100:+6.2f}%")
    return out


def main():
    lines = []
    out = lambda s="": (lines.append(s), print(s))  # noqa: E731
    games = G.load()
    params, _ = M.load_settings()
    recs, _ = M.run(games, **params)
    sigma = fit_sigma(games, DEV)
    rows = build_rows(games, recs, sigma)
    out(f"{len(games)} games. Margin std-dev around the spread (fit on DEV): {sigma}")
    selected = {}
    for market in MARKETS:
        res, (bb, sb, n) = screen(rows, market)
        out(f"\n=== {market.upper()}  DEV 2013-14..2018-19  ({n} games) ===")
        out(f"  market calibration: intercept {bb[0]:+.3f} (z {bb[0] / sb[0]:+.1f})   slope on logit(p) {bb[1]:.3f} "
            f"(z vs 1: {(bb[1] - 1) / sb[1]:+.1f})")
        out(f"  {'feature':<16}{'coef':>9}{'z':>7}  halves agree  selected")
        for x in sorted(res, key=lambda d: -abs(d["z"])):
            out(f"  {x['feat']:<16}{x['coef']:>+9.4f}{x['z']:>+7.2f}  {'yes' if x['stable'] else 'no ':<12}  "
                f"{'<== SELECTED' if x['selected'] else ''}")
        selected[market] = [x["feat"] for x in res if x["selected"]]
    out(f"\nSelected on DEV: { {m: v or ['(none)'] for m, v in selected.items()} }")
    if "--test" in sys.argv:
        out("\n" + "=" * 78)
        out("OUT-OF-SAMPLE TEST 2019-20..2025-26 (expanding-window refit, consensus closing prices)")
        out("=" * 78)
        for market in MARKETS:
            for label, feats in (("market calibration only", []), ("+ selected features", selected[market])):
                if label.startswith("+") and not feats:
                    continue
                res = test_market(rows, market, feats)
                out(f"\n{market.upper()}: {label} {feats if feats else ''}")
                out(f"  log loss  model {res['ll_model']:.5f}  vs market {res['ll_mkt']:.5f}  "
                    f"({'model' if res['ll_model'] < res['ll_mkt'] else 'market'} better, {res['n']} games)")
                for thr in EV_THRESHOLDS:
                    out(f"  EV > {thr * 100:.0f}%: {summarize(res['bets'][thr])}")
        out("\nBlind baselines, 2019-20..2025-26 at closing prices:")
        for s in blind(rows):
            out(s)
        OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        out("\nDEV only. Run with --test for the one-time out-of-sample check.")


if __name__ == "__main__":
    main()
