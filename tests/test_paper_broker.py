import json
import tempfile
import unittest
from pathlib import Path

from trading_agent.paper.broker import apply_paper_intent
from trading_agent.policy.models import OrderIntent, PolicyDecision


class PaperBrokerTests(unittest.TestCase):
    def test_apply_buy_intent_initializes_account_and_updates_position(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            decision = PolicyDecision(
                trading_mode="paper",
                checked_symbols=["NVDA"],
                decision="would_trade",
                intent=OrderIntent(
                    symbol="NVDA",
                    side="buy",
                    order_type="limit",
                    limit_price=100.0,
                    estimated_notional=10.0,
                    quantity=0.1,
                    reason_codes=["score_pass"],
                    confidence=0.85,
                ),
            )

            result = apply_paper_intent(root, run_date="2026-06-14", decision=decision, starting_cash=25.0)

            account = json.loads((root / "state" / "runs" / "2026-06-14" / "paper" / "account.json").read_text(encoding="utf-8"))
            positions = json.loads((root / "state" / "runs" / "2026-06-14" / "paper" / "positions.json").read_text(encoding="utf-8"))
            order_line = (root / "state" / "runs" / "2026-06-14" / "paper" / "orders.jsonl").read_text(encoding="utf-8").splitlines()[0]
            order = json.loads(order_line)
            usage = json.loads((root / "state" / "runs" / "2026-06-14" / "planner" / "daily_usage.json").read_text(encoding="utf-8"))

        self.assertTrue(result.applied)
        self.assertEqual(account["cash"], 15.0)
        self.assertEqual(positions["NVDA"]["quantity"], 0.1)
        self.assertEqual(positions["NVDA"]["average_cost"], 100.0)
        self.assertEqual(order["symbol"], "NVDA")
        self.assertEqual(order["side"], "buy")
        self.assertEqual(order["status"], "filled")
        self.assertEqual(usage["date"], "2026-06-14")
        self.assertEqual(usage["used_notional"], 10.0)
        self.assertEqual(usage["paper_filled_notional"], 10.0)
        self.assertEqual(usage["paper_order_count"], 1)

    def test_apply_buy_intent_accumulates_existing_daily_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            usage_path = root / "state" / "runs" / "2026-06-14" / "planner" / "daily_usage.json"
            usage_path.parent.mkdir(parents=True)
            usage_path.write_text(json.dumps({"date": "2026-06-14", "used_notional": 5.5}), encoding="utf-8")
            decision = PolicyDecision(
                trading_mode="paper",
                checked_symbols=["NVDA"],
                decision="would_trade",
                intent=OrderIntent(
                    symbol="NVDA",
                    side="buy",
                    order_type="limit",
                    limit_price=100.0,
                    estimated_notional=10.0,
                    quantity=0.1,
                ),
            )

            result = apply_paper_intent(root, run_date="2026-06-14", decision=decision, starting_cash=25.0)
            usage = json.loads(usage_path.read_text(encoding="utf-8"))

        self.assertTrue(result.applied)
        self.assertEqual(usage["used_notional"], 15.5)
        self.assertEqual(usage["paper_filled_notional"], 10.0)
        self.assertEqual(usage["paper_order_count"], 1)


if __name__ == "__main__":
    unittest.main()
