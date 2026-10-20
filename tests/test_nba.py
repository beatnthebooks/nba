"""NBA edition (nba/): consensus lines, schedule features, no look-ahead in the Elo, exchange price math. No network."""

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nba"))
import games as G  # noqa: E402
import markets as Mk  # noqa: E402
import model as M  # noqa: E402


def book(name, hml, aml, sp, tot, hso=-110, aso=-110, oo=-110, uo=-110):
    return {"p": name, "hml": hml, "aml": aml, "sp": sp, "tot": tot, "hso": hso, "aso": aso, "oo": oo, "uo": uo}


def game(gid, day, home, away, hs=None, as_=None, season=2025, neutral=False):
    return {"gid": gid, "season": season, "stype": 2, "playoff": False, "iso": f"{day}T23:00Z",
            "day": date.fromisoformat(day), "home": home, "away": away, "hcode": "", "acode": "", "neutral": neutral,
            "city": "", "venue": "", "cup_final": False, "hs": hs, "as": as_, "state": "post" if hs is not None else "pre",
            "detail": "", "notes": [], "ot": False, "line": {}, "open": {}}


class Consensus(unittest.TestCase):
    def test_median_and_outlier(self):
        items = [book("DraftKings", -150, 130, -3.5, 220.5), book("MGM", -155, 135, -3.5, 221.5),
                 book("Caesars", -145, 125, -3.0, 220.5),
                 book("Stale Book", 130, -150, 9.5, 213.5),            # mis-keyed: > 3 pts off the median spread
                 book("consensus", -900, 600, -20, 300)]               # not a sportsbook
        c = G.consensus(items)
        self.assertEqual(c["books"], 3)
        self.assertEqual(c["sp"], -3.5)
        self.assertEqual(c["tot"], 220.5)
        self.assertAlmostEqual(c["pml"], G.devig(-150, 130), places=6)

    def test_closing_snapshot_wins(self):
        b = book("ESPN BET", -200, 170, -5.5, 219.5)
        b["c"] = {"hml": -210, "aml": 175, "hsp": -6.5, "tot": 218.5}
        b["o"] = {"hsp": -4.5, "tot": 222.5}
        self.assertEqual(G.consensus([b], "c")["sp"], -6.5)
        self.assertEqual(G.consensus([b], "o")["sp"], -4.5)


class Schedule(unittest.TestCase):
    def test_back_to_back_and_rest(self):
        gs = [game("1", "2025-11-01", 2, 8, 100, 90), game("2", "2025-11-02", 18, 2, 100, 90),
              game("3", "2025-11-05", 2, 18)]
        G.add_schedule_features(gs)
        self.assertTrue(gs[1]["ab2b"])           # Boston played the night before
        self.assertFalse(gs[1]["hb2b"])
        self.assertEqual(gs[2]["hrest"], 3)
        self.assertEqual(gs[0]["hrest"], 7)      # first game of the season


class NoLookAhead(unittest.TestCase):
    def test_result_does_not_change_its_own_prediction(self):
        gs = [game(str(i), f"2025-11-{i + 1:02d}", 1 + i % 4, 5 + i % 3, 100 + i, 95) for i in range(20)]
        G.add_schedule_features(gs)
        p1 = [r["p"] for r in M.run(gs)[0]]
        gs[10]["hs"], gs[10]["as"] = 80, 130                        # flip game 10's result
        p2 = [r["p"] for r in M.run(gs)[0]]
        self.assertEqual(p1[:11], p2[:11])                          # games up to and including 10 unchanged
        self.assertNotEqual(p1[11:], p2[11:])


class ExchangeMath(unittest.TestCase):
    def test_offer_includes_fee(self):
        o = Mk.offer("kalshi", 0.5)
        self.assertAlmostEqual(o["fee"], 0.07 * 0.25 * 100, places=2)
        self.assertAlmostEqual(o["dec"], 1 / (0.5 + 0.0175), places=3)

    def test_fair_prob_sides(self):
        fair = {"home": 0.6, "spreadPoint": -4.5, "spreadHome": 0.52, "totalPoint": 221.5, "over": 0.48}
        self.assertAlmostEqual(Mk._fair_prob(fair, "spread", "home", -4.5), 0.52)
        self.assertAlmostEqual(Mk._fair_prob(fair, "spread", "away", 4.5), 0.48)
        self.assertIsNone(Mk._fair_prob(fair, "spread", "away", 5.5))
        self.assertAlmostEqual(Mk._fair_prob(fair, "total", "under", 221.5), 0.52)


if __name__ == "__main__":
    unittest.main()
