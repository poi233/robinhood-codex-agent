import unittest
from pathlib import Path
from unittest import mock

from trading_agent.growth import leaderboard
from trading_agent.growth.leaderboard import _equity_stats, build_leaderboard


def _eq(*vals: float) -> list[dict]:
    return [{"timestamp": f"2026-06-{10 + i:02d}T13:00:00Z", "total_equity": v} for i, v in enumerate(vals)]


class EquityStatsTests(unittest.TestCase):
    def test_total_return_days_last_equity(self):
        stats = _equity_stats(_eq(1000.0, 1100.0, 1210.0))
        self.assertEqual(stats["days"], 3)
        self.assertAlmostEqual(stats["total_return"], 0.21, places=6)
        self.assertEqual(stats["last_equity"], 1210.0)

    def test_empty(self):
        stats = _equity_stats([])
        self.assertIsNone(stats["total_return"])
        self.assertEqual(stats["days"], 0)


class BuildLeaderboardTests(unittest.TestCase):
    def _build(self, *, min_filled: int) -> dict:
        report = {
            "generated_at": "t",
            "champion": {"filled": 30, "max_drawdown": 0.05, "fill_rate_pct": 90.0},
            "challengers": [
                {"challenger_strategy_id": "A", "metrics": {"filled": 25, "max_drawdown": 0.03, "realized_pnl": 500.0}},
                {"challenger_strategy_id": "B", "metrics": {"filled": 2, "max_drawdown": 0.5, "realized_pnl": 5000.0}},
            ],
        }
        equity = {None: _eq(1000.0, 1010.0), "A": _eq(1000.0, 1050.0), "B": _eq(1000.0, 1300.0)}

        def fake_load_equity(agent_root, *, run_dates, challenger_id):
            return equity[challenger_id]

        with mock.patch.object(leaderboard, "discover_run_dates", return_value=["2026-06-10", "2026-06-11"]), \
            mock.patch.object(leaderboard, "evaluate_experiments", return_value=report), \
            mock.patch.object(leaderboard, "_load_equity_points", side_effect=fake_load_equity), \
            mock.patch.object(leaderboard, "load_growth_policy", return_value={"promotion_rules": {"min_filled_trades": min_filled}}), \
            mock.patch("trading_agent.strategy.registry.load_active_strategy", return_value={"strategy_id": "champ_v1"}):
            return build_leaderboard(Path("/x"))

    def test_sorted_by_return_and_leader_respects_min_filled(self):
        lb = self._build(min_filled=20)
        ids = [r["strategy_id"] for r in lb["strategies"]]
        self.assertEqual(ids, ["B", "A", "champ_v1"])  # total_return desc: 30%, 5%, 1%
        # B leads on return (+30%) but has only 2 fills < 20 → skipped; A (+5%, 25 fills) is leader.
        self.assertEqual(lb["leader"], "A")
        self.assertTrue(next(r for r in lb["strategies"] if r["strategy_id"] == "A")["is_leader"])
        champ = next(r for r in lb["strategies"] if r["strategy_id"] == "champ_v1")
        self.assertEqual(champ["role"], "champion")  # champion is just a row, keyed by its registry id

    def test_gate_off_leader_is_top_return(self):
        lb = self._build(min_filled=0)
        self.assertEqual(lb["leader"], "B")  # no guardrail → top return wins
        self.assertTrue(lb["leader_qualified"])


if __name__ == "__main__":
    unittest.main()
