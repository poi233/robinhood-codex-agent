import unittest

from trading_agent.replay.significance import (
    benjamini_hochberg,
    binomial_sf,
    combine_equal_weight_returns,
    max_drawdown_from_returns,
    portfolio_metrics,
    sharpe,
)


class BinomialTests(unittest.TestCase):
    def test_known_values(self):
        # binomial_sf rounds to 6 dp, so compare at 5 places.
        self.assertAlmostEqual(binomial_sf(10, 10), 1 / 1024, places=5)   # all wins
        self.assertAlmostEqual(binomial_sf(8, 10), 56 / 1024, places=5)   # >=8 of 10
        self.assertAlmostEqual(binomial_sf(5, 10), 638 / 1024, places=5)  # >=5 of 10 (~coin)

    def test_edge_cases(self):
        self.assertIsNone(binomial_sf(3, 0))   # no trials
        self.assertEqual(binomial_sf(0, 10), 1.0)  # zero wins → certain to see >= 0


class BenjaminiHochbergTests(unittest.TestCase):
    def test_controls_false_discovery(self):
        result = benjamini_hochberg({"A": 0.001, "B": 0.01, "C": 0.04, "D": 0.5}, alpha=0.05)
        significant = {k for k, v in result.items() if v["significant"]}
        self.assertEqual(significant, {"A", "B"})
        self.assertAlmostEqual(result["A"]["q"], 0.004, places=4)
        self.assertAlmostEqual(result["B"]["q"], 0.02, places=4)
        # q-values are monotone non-decreasing with p
        self.assertLessEqual(result["A"]["q"], result["B"]["q"])
        self.assertLessEqual(result["B"]["q"], result["C"]["q"])

    def test_empty_and_none(self):
        result = benjamini_hochberg({"A": None}, alpha=0.05)
        self.assertFalse(result["A"]["significant"])


class PortfolioStatsTests(unittest.TestCase):
    def test_sharpe_none_on_zero_vol_or_short(self):
        self.assertIsNone(sharpe([0.01, 0.01, 0.01]))  # zero variance
        self.assertIsNone(sharpe([0.01]))  # too short
        self.assertIsInstance(sharpe([0.01, -0.01, 0.02, 0.0]), float)

    def test_max_drawdown(self):
        self.assertEqual(max_drawdown_from_returns({"d1": 0.1, "d2": -0.5, "d3": 0.1}), 0.5)
        self.assertIsNone(max_drawdown_from_returns({"d1": 0.1}))  # single point

    def test_combine_equal_weight(self):
        combined = combine_equal_weight_returns({"A": {"d1": 0.1, "d2": 0.2}, "B": {"d1": 0.0}}, ["A", "B"])
        self.assertAlmostEqual(combined["d1"], 0.05)  # mean of 0.1 and 0.0
        self.assertAlmostEqual(combined["d2"], 0.2)   # only A traded d2

    def test_portfolio_metrics(self):
        metrics = portfolio_metrics({"A": {"d1": 0.1, "d2": 0.2}, "B": {"d1": 0.0}}, ["A", "B"])
        self.assertEqual(metrics["days"], 2)
        self.assertAlmostEqual(metrics["cumulative_return"], 1.05 * 1.2 - 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
