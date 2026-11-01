import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from _load import load

macro = load("trader-macro", "forecast")


class TestDualEngineMacro(unittest.TestCase):
    def test_strong_usd_dominance(self):
        # US stocks severely outperform counter basket -> DXY surges, Gold drops
        res = macro.classify_differential(net_diff=1.20)
        self.assertEqual(res["regime"], "STRONG_USD_DOMINANCE")
        self.assertIn("BEARISH", res["gold_forecast"])
        self.assertIn("BULLISH", res["dxy_bias"])
        self.assertEqual(res["gold_signal"], "STRONG SELL / SHORT")

    def test_mild_usd_dominance(self):
        res = macro.classify_differential(net_diff=0.30)
        self.assertEqual(res["regime"], "MILD_USD_DOMINANCE")
        self.assertIn("BEARISH", res["gold_forecast"])
        self.assertIn("BULLISH", res["dxy_bias"])

    def test_strong_counter_dominance(self):
        # European/Asian counter stocks rally hard -> DXY falls, Gold rallies
        res = macro.classify_differential(net_diff=-0.80)
        self.assertEqual(res["regime"], "STRONG_COUNTER_DOMINANCE")
        self.assertIn("BULLISH", res["gold_forecast"])
        self.assertIn("BEARISH", res["dxy_bias"])
        self.assertEqual(res["gold_signal"], "STRONG BUY / LONG")

    def test_mild_counter_dominance(self):
        res = macro.classify_differential(net_diff=-0.25)
        self.assertEqual(res["regime"], "MILD_COUNTER_DOMINANCE")
        self.assertIn("BULLISH", res["gold_forecast"])
        self.assertIn("BEARISH", res["dxy_bias"])

    def test_equilibrium(self):
        res = macro.classify_differential(net_diff=0.02)
        self.assertEqual(res["regime"], "EQUILIBRIUM")
        self.assertIn("RANGE-BOUND", res["gold_forecast"])
        self.assertIn("NEUTRAL", res["dxy_bias"])

    def test_parse_yahoo(self):
        sample = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "regularMarketPrice": 2750.50,
                            "previousClose": 2700.00,
                            "regularMarketDayHigh": 2760.00,
                            "regularMarketDayLow": 2695.00,
                            "regularMarketTime": 1730000000,
                        }
                    }
                ]
            }
        }
        parsed = macro.parse_yahoo(json.dumps(sample), "GC=F")
        self.assertEqual(parsed["symbol"], "GC=F")
        self.assertEqual(parsed["price"], 2750.50)
        self.assertEqual(parsed["pct_change"], 1.87)
        self.assertEqual(parsed["day_high"], 2760.00)


    def test_failed_fetch_never_masks_as_equilibrium(self):
        # When symbols fail, the engine must mark invalid and refuse to guess 0.00%
        res = macro.classify_differential(net_diff=None)
        self.assertEqual(res["regime"], "DATA_UNAVAILABLE")
        self.assertIn("DATA TIDAK TERSEDIA", res["gold_forecast"])
        self.assertEqual(res["gold_signal"], "NO SIGNAL / HOLD")

    def test_safe_haven_convergence(self):
        # In risk-off panics: DXY rises (cash preference), yields fall (flight to Treasuries), stocks drop.
        # Gold should rally alongside the dollar (Safe Haven Convergence), not be shorted!
        res = macro.classify_differential(
            net_diff=-0.50,
            dxy_pct=0.15,
            us10y_pct=-0.80,
            spy_pct=-1.50
        )
        self.assertEqual(res["regime"], "SAFE_HAVEN_CONVERGENCE")
        self.assertTrue(res["is_safe_haven"])
        self.assertIn("BULLISH", res["gold_forecast"])
        self.assertEqual(res["gold_signal"], "BUY ON DIPS / SAFE-HAVEN ACCUMULATION")

    def test_dual_macro_headwinds(self):
        # DXY surges (+0.30%) and US10Y yields surge (+1.20%): severe pressure on Gold
        res = macro.classify_differential(
            net_diff=1.00,
            dxy_pct=0.30,
            us10y_pct=1.20,
            spy_pct=0.10
        )
        self.assertEqual(res["regime"], "DUAL_MACRO_HEADWINDS")
        self.assertIn("BEARISH", res["gold_forecast"])
        self.assertEqual(res["gold_signal"], "STRONG SELL / SHORT")

    def test_dual_macro_tailwinds(self):
        # DXY drops (-0.35%) and US10Y yields fall (-1.10%): massive catalyst for Gold rally
        res = macro.classify_differential(
            net_diff=-0.90,
            dxy_pct=-0.35,
            us10y_pct=-1.10,
            spy_pct=0.50
        )
        self.assertEqual(res["regime"], "DUAL_MACRO_TAILWINDS")
        self.assertIn("BULLISH", res["gold_forecast"])
        self.assertEqual(res["gold_signal"], "STRONG BUY / LONG")

    def test_ice_dxy_basket_weights(self):
        # Official ICE weights must sum to exactly 1.0 (100%)
        total_weight = sum(info["weight"] for info in macro.DXY_FX_PAIRS.values())
        self.assertAlmostEqual(total_weight, 1.0, places=4)

        # Check weights of major components
        self.assertAlmostEqual(macro.DXY_FX_PAIRS["EURUSD"]["weight"], 0.576, places=3)
        self.assertAlmostEqual(macro.DXY_FX_PAIRS["USDJPY"]["weight"], 0.136, places=3)
        self.assertAlmostEqual(macro.DXY_FX_PAIRS["GBPUSD"]["weight"], 0.119, places=3)
        self.assertAlmostEqual(macro.DXY_FX_PAIRS["USDCAD"]["weight"], 0.091, places=3)
        self.assertAlmostEqual(macro.DXY_FX_PAIRS["USDSEK"]["weight"], 0.042, places=3)
        self.assertAlmostEqual(macro.DXY_FX_PAIRS["USDCHF"]["weight"], 0.036, places=3)


if __name__ == "__main__":
    unittest.main()
