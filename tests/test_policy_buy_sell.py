import unittest

from trading_agent.policy.engine import generate_order_intent
from trading_agent.policy.models import OpenOrder, PolicyInputs, Position, Quote


def base_inputs() -> PolicyInputs:
    return PolicyInputs(
        run_date="2026-06-14",
        trading_mode="paper",
        risk_tier=0,
        risk_caps={"max_single_order_notional": 10, "max_daily_notional": 25},
        universe=["NVDA", "SMH"],
        today_allowlist=["NVDA", "SMH"],
        daily_plan={
            "date": "2026-06-14",
            "market_regime": "normal",
            "allowed_actions": ["small_limit_buy", "partial_take_profit", "risk_exit"],
            "today_watchlist": ["NVDA", "SMH"],
            "symbol_trade_rules": {
                "NVDA": {"max_notional": 10, "entry_condition": "entry zone"},
                "SMH": {"max_notional": 10, "entry_condition": "entry zone"},
            },
        },
        dynamic_allowlist={
            "date": "2026-06-14",
            "symbol_scores": {
                "NVDA": {"score": 85, "setup": "pullback", "max_notional": 10},
                "SMH": {"score": 70, "setup": "pullback", "max_notional": 10},
            },
        },
        daily_usage={"date": "2026-06-14", "used_notional": 0},
        account={"buying_power": 25.0},
        quotes={
            "NVDA": Quote(symbol="NVDA", price=100.0, previous_close=101.0, timestamp="2026-06-14T09:45:00-07:00"),
            "SMH": Quote(symbol="SMH", price=200.0, previous_close=201.0, timestamp="2026-06-14T09:45:00-07:00"),
        },
    )


class PolicyBuySellTests(unittest.TestCase):
    def test_score_below_threshold_blocks_buy(self) -> None:
        inputs = base_inputs()
        inputs.today_allowlist = ["SMH"]
        inputs.daily_plan["today_watchlist"] = ["SMH"]

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("score_below_threshold", decision.blocked_reasons)
        self.assertIsNone(decision.intent)

    def test_missing_quote_blocks_trade(self) -> None:
        inputs = base_inputs()
        inputs.quotes = {}

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("missing_quote", decision.blocked_reasons)

    def test_open_order_blocks_new_order_for_symbol(self) -> None:
        inputs = base_inputs()
        inputs.open_orders = [OpenOrder(symbol="NVDA", side="buy", quantity=0.1, notional=10)]

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("open_order_exists", decision.blocked_reasons)

    def test_daily_cap_exhausted_blocks_buy(self) -> None:
        inputs = base_inputs()
        inputs.daily_usage = {"date": "2026-06-14", "used_notional": 25}

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("daily_notional_exhausted", decision.blocked_reasons)

    def test_buy_notional_is_capped_by_account_buying_power(self) -> None:
        inputs = base_inputs()
        inputs.account = {"buying_power": 4.25}

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "would_trade")
        self.assertIsNotNone(decision.intent)
        self.assertEqual(decision.intent.estimated_notional, 4.25)

    def test_losing_position_blocks_average_down_buy(self) -> None:
        inputs = base_inputs()
        inputs.positions = {"NVDA": Position(symbol="NVDA", quantity=1, average_cost=110.0, market_price=100.0)}

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("average_down_blocked", decision.blocked_reasons)

    def test_partial_take_profit_generates_sell_intent_before_buy(self) -> None:
        inputs = base_inputs()
        inputs.positions = {"NVDA": Position(symbol="NVDA", quantity=2, average_cost=100.0, market_price=103.0)}
        inputs.quotes["NVDA"] = Quote(symbol="NVDA", price=103.0, previous_close=102.0, timestamp="2026-06-14T09:45:00-07:00")

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "would_trade")
        self.assertIsNotNone(decision.intent)
        self.assertEqual(decision.intent.side, "sell")
        self.assertEqual(decision.intent.symbol, "NVDA")
        self.assertLessEqual(decision.intent.quantity, 2)
        self.assertIn("partial_take_profit", decision.intent.reason_codes)

    def test_short_setup_without_long_position_never_opens_short(self) -> None:
        inputs = base_inputs()
        inputs.dynamic_allowlist["symbol_scores"]["NVDA"]["score"] = 0
        inputs.technical_signals = {
            "symbols": {
                "NVDA": {
                    "short_setup": {"status": "active", "trigger_below": 99.0},
                }
            }
        }

        decision = generate_order_intent(inputs)

        self.assertNotEqual(decision.intent.side if decision.intent else None, "sell")
        self.assertIn(decision.decision, {"blocked", "no_action"})


if __name__ == "__main__":
    unittest.main()
