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

        self.assertTrue(result.applied)
        self.assertEqual(account["cash"], 15.0)
        self.assertEqual(positions["NVDA"]["quantity"], 0.1)
        self.assertEqual(positions["NVDA"]["average_cost"], 100.0)
        self.assertEqual(order["symbol"], "NVDA")
        self.assertEqual(order["side"], "buy")
        self.assertEqual(order["status"], "filled")


if __name__ == "__main__":
    unittest.main()
