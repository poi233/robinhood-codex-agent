import json
import tempfile
import unittest
from pathlib import Path

from trading_agent.paper.broker import apply_paper_intent, record_paper_day_end, record_paper_day_start
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
            day_start = json.loads((root / "state" / "runs" / "2026-06-14" / "paper" / "day_start.json").read_text(encoding="utf-8"))
            curve = [
                json.loads(line)
                for line in (root / "state" / "runs" / "2026-06-14" / "paper" / "equity_curve.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]

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
        self.assertEqual(day_start["cash"], 25.0)
        self.assertEqual(day_start["total_equity"], 25.0)
        self.assertEqual(curve[0]["event"], "day_start")
        self.assertEqual(curve[-1]["event"], "fill")
        self.assertEqual(curve[-1]["cash"], 15.0)
        self.assertEqual(curve[-1]["positions_market_value"], 10.0)
        self.assertEqual(curve[-1]["total_equity"], 25.0)

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

    def test_day_start_is_not_overwritten_and_day_end_records_current_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            first = record_paper_day_start(root, run_date="2026-06-14", starting_cash=25.0)
            second = record_paper_day_start(root, run_date="2026-06-14", starting_cash=99.0)
            result = record_paper_day_end(root, run_date="2026-06-14")

            paper_dir = root / "state" / "runs" / "2026-06-14" / "paper"
            day_start = json.loads((paper_dir / "day_start.json").read_text(encoding="utf-8"))
            day_end = json.loads((paper_dir / "day_end.json").read_text(encoding="utf-8"))
            curve = [json.loads(line) for line in (paper_dir / "equity_curve.jsonl").read_text(encoding="utf-8").splitlines()]

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertTrue(result)
        self.assertEqual(day_start["cash"], 25.0)
        self.assertEqual(day_end["cash"], 25.0)
        self.assertEqual(day_end["total_equity"], 25.0)
        self.assertEqual([point["event"] for point in curve], ["day_start", "day_end"])


if __name__ == "__main__":
    unittest.main()
