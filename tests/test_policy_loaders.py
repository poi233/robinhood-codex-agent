import json
import tempfile
import unittest
from pathlib import Path

from trading_agent.policy.loaders import load_policy_inputs


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class PolicyLoaderTests(unittest.TestCase):
    def test_load_policy_inputs_reads_local_config_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "config").mkdir()
            (root / "state").mkdir()
            (root / "config" / "universe.txt").write_text("NVDA\n# comment\nSMH\n", encoding="utf-8")
            (root / "state" / "today_allowlist.txt").write_text("NVDA\nSMH # broad ETF\n", encoding="utf-8")
            write_json(
                root / "config" / "risk_tiers.json",
                {"0": {"max_single_order_notional": 10, "max_daily_notional": 25}},
            )
            write_json(
                root / "state" / "daily_plan.json",
                {
                    "date": "2026-06-14",
                    "market_regime": "normal",
                    "allowed_actions": ["small_limit_buy"],
                    "today_watchlist": ["NVDA"],
                    "symbol_trade_rules": {"NVDA": {"max_notional": 10}},
                },
            )
            write_json(
                root / "state" / "dynamic_allowlist.json",
                {"date": "2026-06-14", "symbol_scores": {"NVDA": {"score": 88}}},
            )
            write_json(root / "state" / "daily_usage.json", {"date": "2026-06-14", "used_notional": 5})
            write_json(
                root / "state" / "research_reports" / "2026-06-14" / "NVDA.json",
                {
                    "date": "2026-06-14",
                    "symbol": "NVDA",
                    "research_bias": "bullish",
                    "risk_flags": [],
                },
            )

            inputs = load_policy_inputs(root, run_date="2026-06-14", trading_mode="paper", risk_tier=0)

        self.assertEqual(inputs.universe, ["NVDA", "SMH"])
        self.assertEqual(inputs.today_allowlist, ["NVDA", "SMH"])
        self.assertEqual(inputs.risk_caps["max_single_order_notional"], 10)
        self.assertEqual(inputs.daily_plan["date"], "2026-06-14")
        self.assertEqual(inputs.dynamic_allowlist["symbol_scores"]["NVDA"]["score"], 88)
        self.assertEqual(inputs.daily_usage["used_notional"], 5)
        self.assertEqual(inputs.research_reports["NVDA"]["research_bias"], "bullish")

    def test_missing_required_state_is_represented_for_fail_closed_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "config").mkdir()
            (root / "state").mkdir()
            (root / "config" / "universe.txt").write_text("NVDA\n", encoding="utf-8")
            write_json(
                root / "config" / "risk_tiers.json",
                {"0": {"max_single_order_notional": 10, "max_daily_notional": 25}},
            )

            inputs = load_policy_inputs(root, run_date="2026-06-14", trading_mode="paper", risk_tier=0)

        self.assertIsNone(inputs.daily_plan)
        self.assertEqual(inputs.today_allowlist, [])
        self.assertEqual(inputs.dynamic_allowlist, {})
        self.assertEqual(inputs.daily_usage, {})


if __name__ == "__main__":
    unittest.main()
