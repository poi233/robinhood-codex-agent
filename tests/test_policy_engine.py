import unittest

from trading_agent.policy.engine import generate_order_intent
from trading_agent.policy.models import PolicyInputs, Quote


def base_inputs(*, trading_mode: str = "paper") -> PolicyInputs:
    return PolicyInputs(
        run_date="2026-06-14",
        trading_mode=trading_mode,
        risk_tier=0,
        risk_caps={"max_single_order_notional": 10, "max_daily_notional": 25},
        universe=["NVDA"],
        today_allowlist=["NVDA"],
        daily_plan={
            "date": "2026-06-14",
            "market_regime": "normal",
            "allowed_actions": ["small_limit_buy", "partial_take_profit"],
            "today_watchlist": ["NVDA"],
            "symbol_trade_rules": {
                "NVDA": {
                    "max_notional": 10,
                    "breakout_allowed": False,
                    "entry_condition": "price in entry zone",
                }
            },
        },
        dynamic_allowlist={
            "date": "2026-06-14",
            "symbol_scores": {
                "NVDA": {
                    "score": 85,
                    "setup": "pullback",
                    "max_notional": 10,
                }
            },
        },
        daily_usage={"date": "2026-06-14", "used_notional": 0},
        quotes={"NVDA": Quote(symbol="NVDA", price=100.0, previous_close=101.0, timestamp="2026-06-14T09:45:00-07:00")},
    )


class PolicyEngineTests(unittest.TestCase):
    def test_missing_daily_plan_blocks_decision(self) -> None:
        inputs = base_inputs()
        inputs.daily_plan = None

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("missing_daily_plan", decision.blocked_reasons)
        self.assertIsNone(decision.intent)

    def test_paper_mode_returns_would_trade_for_valid_buy_candidate(self) -> None:
        decision = generate_order_intent(base_inputs())

        self.assertEqual(decision.decision, "would_trade")
        self.assertIsNotNone(decision.intent)
        self.assertEqual(decision.intent.symbol, "NVDA")
        self.assertEqual(decision.intent.side, "buy")
        self.assertEqual(decision.action_taken, "none")

    def test_review_mode_blocks_execution_when_unwired(self) -> None:
        decision = generate_order_intent(base_inputs(trading_mode="review"))

        self.assertEqual(decision.decision, "blocked")
        self.assertIsNotNone(decision.intent)
        self.assertIn("execution_not_wired", decision.blocked_reasons)
        self.assertEqual(decision.action_taken, "none")

    def test_policy_decision_serializes_to_intraday_json_shape(self) -> None:
        decision = generate_order_intent(base_inputs())

        payload = decision.to_json_dict(timestamp="2026-06-14T09:45:00-0700")

        self.assertEqual(payload["timestamp"], "2026-06-14T09:45:00-0700")
        self.assertEqual(payload["run_kind"], "intraday")
        self.assertEqual(payload["trading_mode"], "paper")
        self.assertEqual(payload["decision"], "would_trade")
        self.assertEqual(payload["action_taken"], "none")
        self.assertEqual(payload["proposed_order"]["symbol"], "NVDA")
        self.assertIsNone(payload["order_id_if_any"])


if __name__ == "__main__":
    unittest.main()
