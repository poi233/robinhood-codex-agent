import unittest
from datetime import datetime

from trading_agent.core.time import PT
from trading_agent.policy.engine import generate_order_intent
from trading_agent.policy.models import OpenOrder, PolicyInputs, Position, Quote


def base_inputs() -> PolicyInputs:
    fresh_timestamp = datetime.now(tz=PT).isoformat()
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
        candidate_scores={
            "date": "2026-06-14",
            "symbols": {
                "NVDA": {"score": 85, "total_score": 85, "components": {"technical": 78, "catalyst": 70}},
                "SMH": {"score": 70, "total_score": 70, "components": {"technical": 68, "catalyst": 60}},
            },
        },
        risk_overlay={
            "date": "2026-06-14",
            "market_regime": "aggressive_ok",
            "max_single_order_notional": 10,
            "max_daily_notional": 25,
            "symbol_trade_rules": {
                "NVDA": {"max_notional": 10, "allow_buy": True},
                "SMH": {"max_notional": 10, "allow_buy": True},
            },
        },
        trader_watch_levels={
            "symbols": {
                "NVDA": {
                    "entry_low": 99.5,
                    "entry_high": 100.5,
                    "buy_trigger_above": 100.5,
                    "do_not_chase_above": 102.0,
                    "no_trade_low": 100.6,
                    "no_trade_high": 100.9,
                    "invalidation_below": 99.0,
                    "risk_reduction_trigger_below": 98.5,
                    "risk_reduction_target_1": 97.5,
                    "risk_reduction_target_2": 96.0,
                    "target_1": 103.0,
                    "target_2": 105.0,
                },
                "SMH": {
                    "entry_low": 198.0,
                    "entry_high": 200.5,
                    "buy_trigger_above": 201.0,
                    "do_not_chase_above": 203.0,
                    "no_trade_low": 200.6,
                    "no_trade_high": 200.9,
                    "invalidation_below": 196.0,
                    "risk_reduction_trigger_below": 197.0,
                    "risk_reduction_target_1": 195.0,
                    "risk_reduction_target_2": 192.0,
                    "target_1": 205.0,
                    "target_2": 208.0,
                },
            }
        },
        data_status_summary={"execution_blocking": False, "reason_codes": []},
        capital_snapshot={"sizing_buying_power": 25.0},
        catalyst_snapshot={"symbols": {"NVDA": {"score": 70}, "SMH": {"score": 60}}},
        policy_profile={
            "name": "aggressive_growth",
            "per_trade_risk_pct": 0.005,
            "cash_buffer_pct": 0.1,
            "pullback_score_threshold": 82,
            "breakout_score_threshold": 88,
            "technical_min_score": 70,
            "min_reward_risk": 1.5,
            "breakout_chase_tolerance_pct": 0.002,
            "minimum_trade_notional": 1.0
        },
        daily_usage={"date": "2026-06-14", "used_notional": 0},
        account={"buying_power": 25.0},
        quotes={
            "NVDA": Quote(symbol="NVDA", price=100.0, previous_close=101.0, timestamp=fresh_timestamp),
            "SMH": Quote(symbol="SMH", price=200.0, previous_close=201.0, timestamp=fresh_timestamp),
        },
        technical_signals={
            "symbols": {
                "NVDA": {
                    "long_setup": {
                        "status": "active",
                        "trigger_above": 100.5,
                        "entry_zone": {"low": 99.5, "high": 100.5},
                        "invalidation_below": 99.0,
                        "target_1": 103.0,
                        "target_2": 105.0,
                        "do_not_chase_above": 102.0,
                    },
                    "short_setup": {
                        "status": "watch",
                        "trigger_below": 98.5,
                        "target_1": 97.5,
                        "target_2": 96.0,
                    },
                    "no_trade_zone": {"low": 100.6, "high": 100.9, "reason": "range chop"},
                },
                "SMH": {
                    "long_setup": {
                        "status": "active",
                        "trigger_above": 201.0,
                        "entry_zone": {"low": 198.0, "high": 200.5},
                        "invalidation_below": 196.0,
                        "target_1": 205.0,
                        "target_2": 208.0,
                        "do_not_chase_above": 203.0,
                    },
                    "short_setup": {
                        "status": "watch",
                        "trigger_below": 197.0,
                        "target_1": 195.0,
                        "target_2": 192.0,
                    },
                    "no_trade_zone": {"low": 200.6, "high": 200.9, "reason": "range chop"},
                },
            }
        },
    )


class PolicyBuySellTests(unittest.TestCase):
    def test_score_below_threshold_blocks_buy(self) -> None:
        inputs = base_inputs()
        inputs.today_allowlist = ["SMH"]
        inputs.daily_plan["today_watchlist"] = ["SMH"]

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("outside_entry_zone", decision.blocked_reasons)
        self.assertIsNone(decision.intent)
        # E3 capture: the block reason is attributed to the specific candidate, not only aggregated.
        self.assertIn("SMH", decision.per_candidate_blocks)
        self.assertIn("outside_entry_zone", decision.per_candidate_blocks["SMH"])
        serialized = decision.to_json_dict(timestamp="2026-06-17T09:31:00")
        self.assertIn("per_candidate_blocks", serialized)
        self.assertEqual(serialized["per_candidate_blocks"]["SMH"], decision.per_candidate_blocks["SMH"])

    def test_missing_quote_blocks_trade(self) -> None:
        inputs = base_inputs()
        inputs.quotes = {}

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("missing_quote", decision.blocked_reasons)

    def test_open_order_blocks_new_order_for_symbol(self) -> None:
        inputs = base_inputs()
        inputs.today_allowlist = ["NVDA"]
        inputs.daily_plan["today_watchlist"] = ["NVDA"]
        inputs.open_orders = [OpenOrder(symbol="NVDA", side="buy", quantity=0.1, notional=10)]

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("open_order_exists", decision.blocked_reasons)

    def test_daily_cap_exhausted_blocks_buy(self) -> None:
        inputs = base_inputs()
        inputs.daily_usage = {"date": "2026-06-14", "used_notional": 25}

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("minimum_trade_notional_blocked", decision.blocked_reasons)

    def test_buy_notional_is_capped_by_account_buying_power(self) -> None:
        inputs = base_inputs()
        inputs.account = {"buying_power": 4.25}

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "would_trade")
        self.assertIsNotNone(decision.intent)
        self.assertLessEqual(decision.intent.estimated_notional, 4.25)
        self.assertGreater(decision.intent.quantity, 0)

    def test_losing_position_blocks_average_down_buy(self) -> None:
        inputs = base_inputs()
        inputs.today_allowlist = ["NVDA"]
        inputs.daily_plan["today_watchlist"] = ["NVDA"]
        inputs.positions = {"NVDA": Position(symbol="NVDA", quantity=1, average_cost=110.0, market_price=100.0)}

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("average_down_blocked", decision.blocked_reasons)

    def test_partial_take_profit_generates_sell_intent_before_buy(self) -> None:
        inputs = base_inputs()
        inputs.positions = {"NVDA": Position(symbol="NVDA", quantity=2, average_cost=100.0, market_price=103.0)}
        inputs.quotes["NVDA"] = Quote(symbol="NVDA", price=103.0, previous_close=102.0, timestamp=datetime.now(tz=PT).isoformat())

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "would_trade")
        self.assertIsNotNone(decision.intent)
        self.assertEqual(decision.intent.side, "sell")
        self.assertEqual(decision.intent.symbol, "NVDA")
        self.assertLessEqual(decision.intent.quantity, 2)
        self.assertEqual(decision.intent.quantity, 0.5)
        self.assertIn("partial_take_profit", decision.intent.reason_codes)

    def test_buy_blocks_when_price_is_in_no_trade_zone(self) -> None:
        inputs = base_inputs()
        inputs.quotes["NVDA"] = Quote(symbol="NVDA", price=100.7, previous_close=101.0, timestamp=datetime.now(tz=PT).isoformat())

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("no_trade_zone", decision.blocked_reasons)

    def test_buy_size_is_reduced_when_technical_stop_is_wide(self) -> None:
        inputs = base_inputs()
        inputs.trader_watch_levels["symbols"]["NVDA"]["invalidation_below"] = 98.0
        inputs.technical_signals["symbols"]["NVDA"]["long_setup"]["invalidation_below"] = 98.0

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "would_trade")
        self.assertIsNotNone(decision.intent)
        self.assertLess(decision.intent.estimated_notional, 10.0)
        self.assertIn("risk_sizing_ok", decision.intent.reason_codes)

    def test_risk_exit_uses_technical_trigger_and_scales_sell_quantity(self) -> None:
        inputs = base_inputs()
        inputs.positions = {"NVDA": Position(symbol="NVDA", quantity=4, average_cost=100.0, market_price=97.0)}
        inputs.quotes["NVDA"] = Quote(symbol="NVDA", price=97.0, previous_close=100.0, timestamp=datetime.now(tz=PT).isoformat())
        inputs.dynamic_allowlist["symbol_scores"]["NVDA"]["score"] = 0

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "would_trade")
        self.assertIsNotNone(decision.intent)
        self.assertEqual(decision.intent.side, "sell")
        self.assertEqual(decision.intent.quantity, 4.0)
        self.assertIn("risk_exit", decision.intent.reason_codes)

    def test_short_setup_without_long_position_never_opens_short(self) -> None:
        inputs = base_inputs()
        inputs.dynamic_allowlist["symbol_scores"]["NVDA"]["score"] = 0
        inputs.candidate_scores["symbols"]["NVDA"]["score"] = 0
        inputs.candidate_scores["symbols"]["NVDA"]["total_score"] = 0
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
